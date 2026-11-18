import argparse

from .core import (Downloader, Event, Fatal, Finished, PlaylistFound, TrackConverting, TrackDone, TrackFailed, TrackProgress)

def show(event: Event) -> None:
    if isinstance(event, PlaylistFound):
        print(f"Playlist found: {event.title} ({event.total} tracks)")
    elif isinstance(event, TrackProgress):
        print(f"[{event.index}/{event.total}] Downloading: {event.title} ({event.track_percent:.2f}% complete, {event.overall_percent:.2f}% overall)")
    elif isinstance(event, TrackConverting):
        print(f"[{event.index}/{event.total}] Converting: {event.title}")
    elif isinstance(event, TrackDone):
        print(f"[{event.index}/{event.total}] Done: {event.title}")
    elif isinstance(event, TrackFailed):
        print(f"[{event.index}/{event.total}] Failed: {event.title} - Error: {event.error}")
    elif isinstance(event, Finished):
        status = "cancelled" if event.cancelled else "completed"
        print(f"Download {status}: {event.succeeded} succeeded, {event.failed} failed")
    elif isinstance(event, Fatal):
        print(f"Fatal error: {event.message}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Download a playlist from YouTube.")
    parser.add_argument("url", help="The URL of the playlist to download.")
    parser.add_argument("--o", "-out", default="downloads", help="The output directory for downloaded files.")
    args = parser.parse_args()

    downloader = Downloader()

    try:
        downloader.download_playlist(args.url, args.out, on_event=show)
    except KeyboardInterrupt:
        downloader.cancel()
        print("\nCancelling")

if __name__ == "__main__":
    main()