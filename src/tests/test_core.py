"""AI-generated tests

These tests replace yt-dlp with a fake, so they need no internet and run in
milliseconds. They test OUR logic: events, failure handling, cancelling.
They cannot tell you whether YouTube still works; only a real run can.
"""
import sys
from pathlib import Path

import pytest
import yt_dlp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ramen_downloader import core  # noqa: E402
from ramen_downloader.core import (Downloader, Fatal, Finished, PlaylistFound,  # noqa: E402
                                   TrackDone, TrackFailed, TrackProgress,
                                   overall_percent, safe_folder_name)

PLAYLIST = {
    "title": "My Mix",
    "uploader": "Some Channel",
    "entries": [
        {"title": "Song A", "webpage_url": "https://x/a"},
        {"title": "Song B", "webpage_url": "https://x/b"},
    ],
}


def make_fake_ydl(playlist=PLAYLIST, fail_urls=(), fetch_error=None):
    """Build a stand-in for yt_dlp.YoutubeDL."""
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            if fetch_error:
                raise RuntimeError(fetch_error)
            return playlist

        def add_post_processor(self, pp, when=None):
            pass

        def download(self, urls):
            if urls[0] in fail_urls:
                raise RuntimeError("boom")
            for hook in self.opts["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 100})
                hook({"status": "finished"})

    return FakeYDL


def run(monkeypatch, tmp_path, on_event=None, downloader=None, **fake_kwargs):
    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", make_fake_ydl(**fake_kwargs))
    events = []

    def collect(e):
        events.append(e)
        if on_event:
            on_event(e)

    (downloader or Downloader()).download_playlist("https://x/list", str(tmp_path), collect)
    return events


def test_happy_path(monkeypatch, tmp_path):
    events = run(monkeypatch, tmp_path)
    assert isinstance(events[0], PlaylistFound) and events[0].total == 2
    assert [type(e) for e in events if isinstance(e, TrackDone)] == [TrackDone, TrackDone]
    last = events[-1]
    assert isinstance(last, Finished)
    assert (last.succeeded, last.failed, last.cancelled) == (2, 0, False)
    assert (tmp_path / "My Mix").is_dir()


def test_one_failure_does_not_stop_the_rest(monkeypatch, tmp_path):
    events = run(monkeypatch, tmp_path, fail_urls={"https://x/a"})
    failed = [e for e in events if isinstance(e, TrackFailed)]
    assert len(failed) == 1 and failed[0].title == "Song A"
    last = events[-1]
    assert (last.succeeded, last.failed) == (1, 1)


def test_fetch_error_is_reported_not_raised(monkeypatch, tmp_path):
    events = run(monkeypatch, tmp_path, fetch_error="no network")
    assert len(events) == 1 and isinstance(events[0], Fatal)
    assert "no network" in events[0].message


def test_cancel_stops_the_job(monkeypatch, tmp_path):
    dl = Downloader()

    def cancel_on_first_progress(e):
        if isinstance(e, TrackProgress):
            dl.cancel()

    events = run(monkeypatch, tmp_path, on_event=cancel_on_first_progress, downloader=dl)
    last = events[-1]
    assert isinstance(last, Finished) and last.cancelled
    assert not any(isinstance(e, TrackDone) for e in events)
    assert not any(isinstance(e, TrackFailed) for e in events)  # cancel is not an error


def test_single_video_instead_of_playlist(monkeypatch, tmp_path):
    single = {"title": "Lonely Song", "uploader": "Me", "webpage_url": "https://x/s"}
    events = run(monkeypatch, tmp_path, playlist=single)
    assert events[0].total == 1
    assert events[-1].succeeded == 1


def test_overall_percent():
    assert overall_percent(1, 10, 0) == 0
    assert overall_percent(3, 10, 50) == pytest.approx(25.0)   # 2.5 of 10 tracks
    assert overall_percent(10, 10, 100) == 100
    assert overall_percent(1, 0, 50) == 0                      # no division by zero


def test_safe_folder_name():
    assert safe_folder_name('AC/DC: "Hits"?') == "ACDC Hits"
    assert safe_folder_name("???") == "Playlist"


def test_cancel_exception_exists_in_installed_ytdlp():
    # If a future yt-dlp removes this, we want to find out from a test, not a user.
    assert hasattr(yt_dlp.utils, "DownloadCancelled")