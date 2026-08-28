import os
from tkinter import messagebox

import yt_dlp
from yt_dlp.postprocessor import PostProcessor


class MetadataInjector(PostProcessor):
    """Sets album/artist/track on the info dict before FFmpegMetadata writes tags.

    (Registered with when='pre_process' so it runs before extraction/download,
    unlike add_postprocessor_hook which only reports progress and can't edit info.)
    """

    def __init__(self, album, artist, track_num):
        super().__init__()
        self.album = album
        self.artist = artist
        self.track_num = track_num

    def run(self, info):
        info['album'] = self.album
        info['artist'] = self.artist
        info['track'] = str(self.track_num)
        return [], info


class Downloader:
    def __init__(self):
        self.cancel_download = False

    def download_playlist_as_mp3(self, playlist_url, download_path='.',
                                  progress_callback=None, status_callback=None):
        self.cancel_download = False  # Reset cancellation flag

        # Shared options for both the info-only fetch and the real downloads.
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignore_no_formats_error': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],  # workaround for signature issues
                }
            },
        }

        # Fetch playlist information
        with yt_dlp.YoutubeDL(common_opts) as ydl:
            try:
                playlist_info = ydl.extract_info(playlist_url, download=False)
                playlist_title = playlist_info.get('title', 'Unknown Playlist')
                playlist_author = playlist_info.get('uploader') or playlist_info.get('channel', 'Unknown Artist')
                track_list = playlist_info.get('entries', [])

                # Filter out None entries (deleted/unavailable videos)
                track_list = [track for track in track_list if track is not None]

            except Exception as e:
                print(f"Error extracting playlist info: {e}")
                if status_callback:
                    status_callback("Error: Failed to extract playlist info")
                messagebox.showerror("Error", "Failed to extract playlist info")
                return

        # Create folder for downloads
        safe_playlist_title = "".join(
            c for c in playlist_title if c.isalnum() or c in (' ', '-', '_')
        ).rstrip()
        download_path = os.path.join(download_path, safe_playlist_title)
        os.makedirs(download_path, exist_ok=True)

        total_tracks = len(track_list)
        completed_tracks = 0

        if status_callback:
            status_callback(f"Found {total_tracks} tracks in playlist: {playlist_title}")

        # Download each track
        for current_track_index, track in enumerate(track_list, start=1):
            if self.cancel_download:
                if status_callback:
                    status_callback("Download cancelled")
                break

            if not track:
                completed_tracks += 1
                continue

            track_url = track.get('webpage_url')
            if not track_url:
                completed_tracks += 1
                continue

            track_title = track.get('title', f'Track {current_track_index}')
            track_author = track.get('uploader') or playlist_author

            if status_callback:
                status_callback(f"Downloading ({current_track_index}/{total_tracks}): {track_title}")

            # Progress tracking for current track
            current_track_progress = 0

            def progress_hook(d):
                nonlocal current_track_progress
                if self.cancel_download:
                    raise Exception("Download cancelled by user")

                if d['status'] == 'downloading':
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    if total_bytes > 0 and progress_callback:
                        current_track_progress = downloaded_bytes / total_bytes * 100
                        cumulative_progress = self.calculate_cumulative_progress(
                            completed_tracks, current_track_progress, current_track_index, total_tracks
                        )
                        progress_callback(cumulative_progress, current_track_index, total_tracks,
                                           track_title, current_track_progress)

                elif d['status'] == 'finished':
                    if progress_callback and status_callback:
                        status_callback(f"Converting: {track_title}")
                        cumulative_progress = self.calculate_cumulative_progress(
                            completed_tracks, 100, current_track_index, total_tracks
                        )
                        progress_callback(cumulative_progress, current_track_index, total_tracks,
                                           track_title, 100)

            ydl_opts = {
                **common_opts,
                'outtmpl': f'{download_path}/%(title)s.%(ext)s',
                'format': 'bestaudio/best',
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320',
                    },
                    {
                        'key': 'FFmpegMetadata',
                        'add_metadata': True,
                    },
                ],
                'postprocessor_args': [
                    '-id3v2_version', '4',
                ],
                'progress_hooks': [progress_hook],
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Injects album/artist/track into info dict before download/tagging.
                    ydl.add_post_processor(
                        MetadataInjector(playlist_title, track_author, current_track_index),
                        when='pre_process',
                    )
                    ydl.download([track_url])
                    completed_tracks += 1

            except Exception as e:
                if "cancelled" in str(e).lower():
                    if status_callback:
                        status_callback("Download cancelled by user")
                    break
                print(f"Error downloading track {current_track_index}: {e}")
                if status_callback:
                    status_callback(f"Error downloading: {track_title}")
                # Mark as completed even if error to continue with next tracks
                completed_tracks += 1
                continue

        # Final completion callback
        if not self.cancel_download:
            if progress_callback:
                progress_callback(100, total_tracks, total_tracks, "Complete", 100)
            if status_callback:
                status_callback("Download completed successfully!")
            messagebox.showinfo("Success", "Download completed successfully!")
        else:
            if status_callback:
                status_callback("Download cancelled")
            messagebox.showinfo("Cancelled", "Download was cancelled")

    def calculate_cumulative_progress(self, completed_tracks, current_track_progress,
                                       current_track_index, total_tracks):
        """Calculate cumulative progress across all tracks"""
        if total_tracks == 0:
            return 0

        track_weight = 100 / total_tracks
        completed_progress = completed_tracks * track_weight
        current_track_contribution = (current_track_progress / 100) * track_weight
        total_progress = completed_progress + current_track_contribution

        return min(total_progress, 100)

    def cancel_download_func(self):
        self.cancel_download = True