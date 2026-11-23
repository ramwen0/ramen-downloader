from __future__ import annotations

import threading
import time
import uuid 
from typing import Callable, Dict, List, Optional
from .core import (Downloader, Event, Fatal, Finished, PlaylistFound, TrackConverting, TrackDone, TrackFailed, TrackProgress)

FINISHED_STATES = {"done", "cancelled", "error"}

class Job:
    def __init__(self, url:str, downloader):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.downloader = downloader
        self.creatd_at = time.time()

        self._lock = threading.Lock()
        self._version = 0
        self._status = "queued"
        self._error: Optional[str] = None
        self._playlist_title = Optional[str] = None
        self._total = 0
        self._current_index = 0
        self._current_title: Optional[str] = None
        self._track_percent = 0.0
        self._overall_percent = 0.0
        self._tracks: Dict[int, dict] = {}

    # -- reading
    @property
    def version(self) -> int:
        return self._version

    def snapshot(self) -> dict:
        with self._lock:
            tracks = [self._tracks[i] for i in sorted(self._tracks)]
            return {
                "id": self.id,
                "url": self.url,
                "status": self._status,
                "error": self._error,
                "playlist_title": self._playlist_title,
                "total": self._total,
                "current_index": self._current_index,
                "current_title": self._current_title,
                "track_percent": round(self._track_percent, 2),
                "overall_percent": round(self._overall_percent, 2),
                "succeeded": sum(t["status"] == "done" for t in tracks),
                "failed": sum(t["status"] == "failed" for t in tracks),
                "tracks": [dict(t) for t in tracks],
            }

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    # -- writing
    def _set_track(self, index:int, title:str, status:str, error:Optional[str] = None):
        self._tracks[index] = {"index": index, "title": title, "status": status, "error": error}

    def try_start(self) -> bool:
        with self._lock:
            if self._status != "queued":
                return False
            self._status = "running"
            self._version += 1
            return True

    def cancel_if_queued(self) -> None:
        with self._lock:
            if self._status == "queued":
                self._status = "cancelled"
                self._version += 1

    def apply(self, event: Event) -> None:
        with self._lock:
            if isinstance(event, PlaylistFound):
                self._playlist_title = event.title
                self._total = event.total
            elif isinstance(event, TrackProgress):
                self._current_index = event.index
                self._current_title = event.title
                self._track_percent = event.track_percent
                self._overall_percent = event.overall_percent
                self._set_track(event.index, event.title, "downloading")
            elif isinstance(event, TrackConverting):
                self._current_index = event.index
                self._current_title = event.title
                self._set_track(event.index, event.title, "converting")
            elif isinstance(event, TrackDone):
                self._set_track(event.index, event.title, "done")
            elif isinstance(event, TrackFailed):
                self._set_track(event.index, event.title, "failed", event.error)
            elif isinstance(event, Fatal):
                self._status = "error"
                self._error = event.message
            elif isinstance(event, Finished):
                if event.cancelled:
                    self._status = "cancelled"
                else:
                    self._status = "done"
                    self._overall_percent = 100.0
            self._version += 1
        
    class JobManager:
        def __init__(self, music_dir:str, downloader_factory:Callable[[], object] = Downloader, max_concurrent:int = 1):
            self.music_dir = music_dir
            self._factory = downloader_factory
            self._slots = threading.Semaphore(max_concurrent)
            self.jobs = Dict[str, Job] = {}
            self._lock = threading.Lock()

        def create(self, url:str) -> Job:
            job = Job(url, self._factory())
            with self._lock:
                self._jobs[job.id] = job
            threading.Thread(target=self._run, args=(job,), daemon=True).start()
            return job

        def get(self, job_id: str) ->   Optional[Job]:
            with self._lock:
                return self._jobs.get(job_id)

        def list(self) -> List[Job]:
            with self._lock:
                return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

        def cancel(self, job_id:str) -> Optional[Job]:
            job = self.get(job_id)
            if job is None:
                return None
            job.cancel_if_queued()
            job.downloader.cancel()
            return job

        def _run(self, job:Job) -> None:
            with self._slots:
                if not job.try_start():
                    return
                try:
                    job.downloader.download_playlist(job.url, self.music_dir, on_event=job.apply)
                except Exception as exc:
                    job.apply(Fatal(f"Unexpected error: {exc}"))
                
