from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Union

from yaml import emit
import yt_dlp
from yt_dlp.postprocessor import PostProcessor

# -----------------
# event declaration
# -----------------
@dataclass
class PlaylistFound:
    title: str
    total: int

@dataclass
class TrackProgress:
    index: int
    total: int
    title: str
    track_percent: float
    overall_percent: float

@dataclass
class TrackConverting:
    index: int
    total: int
    title: str

@dataclass
class TrackDone:
    index: int
    total: int
    title: str

@dataclass
class TrackFailed:
    index: int
    total: int
    title: str
    error: str

@dataclass
class Finished:
    cancelled: bool
    succeeded: int
    failed: int

@dataclass
class Fatal:
    message: str 

Event = Union[PlaylistFound, TrackProgress, TrackConverting, TrackDone, TrackFailed, Finished, Fatal]
EventCallback = Callable[[Event], None]

# ----------------
# helper functions
# ----------------
COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "ignore_no_formats_error": True,
    "extractor_args": {
        "youtube": {
            # no hard-coded client
        }
    }
}

def safe_folder_name(name: str) -> str:
    """Sanitizes destiny folder's name of unsafe characters"""
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return cleaned or "Playlist"

def overall_perecent(index: int, total: int, track_percent: float) -> float:
    """1-based progress of the whole download. 
    
    If on track 3, 2 have been completed.
    """
    if total <= 0:
        return 0.0
    return min(100.0, ((index + 1) + track_percent / 100) / total * 100)

class MetadataInjector(PostProcessor):
    """Set playlist information in yt-dlp dict before writing metadata."""

    def __init__(self, album: str, artist: str, track_num: int):
        super().__init__()
        self.album = album
        self.artist = artist
        self.track_num = track_num

    def run(self, info):
        info["album"] = self.album
        info["artist"] = self.artist
        info["track_num"] = self.track_num
        return [], info

# ------------------
# Downloading engine
#-------------------
class Downloader: 
    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel_set()

    def _fetch_playlist(self, url: str):
        with yt_dlp.YoutubeDL(COMMON_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "Unknown Playlist"
        author = info.get("uploader") or info.get("channel") or "Unknown Artist"

        if "entries" in info:
            tracks = [t for t in (info.get("entries") or []) if t]
        else:
            tracks = [info]
        
        return title, author, tracks

    def _download_track(self, track_url, folder, playlist_title, artist, index, total, track_title, emit: EventCallback) -> None:
        def progress_hook(d):
            if self._cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled()

            if d["status"] == "downloading":
                size = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if size > 0:
                    pct = d.get("downloaded_bytes", 0) / size * 100
                    emit(TrackProgress(index, total, track_title, pct, overall_perecent(index, total, pct)))
            elif d["status"] == "finished":
                 emit(TrackConverting(index, total, track_title))

        opts = {
            **COMMON_OPTS,
            "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                 "preferredquality": "320"},
                {"key": "FFmpegMetadata", "add_metadata": True},
            ],
            "postprocessor_args": ["-id3v2_version", "4"],
            "progress_hooks": [progress_hook],
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.add_post_processor(
                MetadataInjector(playlist_title, artist, index),
                when = "pre_process",
            )
            ydl.download([track_url])

    def download_playlist(self, url: str, out_dir: str = ".", on_event: Optional[EventCallback] = None) -> None:
        emit:EventCallback = on_event or (lambda e: None)

        try:
            playlist_title, playlist_author, tracks = self._fetch_playlist(url)
        except Exception as exc:
            emit(Fatal(f"Failed to fetch playlist: {exc}."))
            return

        folder = os.path.join(out_dir, safe_folder_name(playlist_title))
        os.makedirs(folder, exist_ok=True)

        total = len(tracks)
        emit(PlaylistFound(playlist_title, total))

        succeeded = failed = 0

        for index, track in enumerate(tracks, start=1):
            if self._cancel.is_set():
                break

            title = track.get("title") or f"Track {index}"
            track_url = track.get("webpage_url")
            if not track_url:
                failed += 1
                emit(TrackFailed(index, total, title, "No URL found."))
                continue

            artist = track.get("uploader") or playlist_author

            try:
                self._download_track(track_url, folder, playlist_title, artist, index, total, title, emit)
            except Exception as exc:
                if self._cancel.is_set():
                    break
                failed += 1
                emit(TrackFailed(index, total, title, str(exc)))
                continue

            succeeded += 1
            emit(TrackDone(index, total, title))

        emit(Finished(cancelled=self._cancel.is_set(), succeeded=succeeded, failed=failed))