from __future__ import annotations

import asyncio
import json
import os
from typing import Optional
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from.jobs import FINISHED_STATES, JobManager

ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "soundcloud.com"
}

class JobRequest(BaseModel):
    url:str

    @field_validator("url")
    @classmethod
    def url_must_be_allowed(cls, value:str) -> str:
        value = value.strip()
        parts = urlparse(value)
        if parts.scheme not in ("http", "https"):
            raise ValueError("URL must follow HTTP protocol.")
        if (parts.hostname or "").lower() not in ALLOWED_HOSTS:
            raise ValueError("Source not supported")
        return value

def create_app(manager: Optional[JobManager] = None) -> FastAPI:
    if manager is None:
        music_dir = os.path.abspath(os.environ.get("RAMEN_MUSIC_DIR", "music"))
        manager = JobManager(music_dir)

    app = FastAPI(title = "Ramen Downloader")

    def get_job_or_404(job_id:str):
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/api/jobs", status_code=201)
    def create_job(body:JobRequest):
        return manager.create(body.url).snapshot()

    @app.get("/api/jobs")
    def list_jobs():
        return [job.snapshot() for job in manager.list()]

    @app.get("/api/jobs/{job_id}")
    def read_job(job_id: str):
        return get_job_or_404(job_id).snapshot()

    @app.post("/api/jobs/{job_id}/events")
    async def job_events(job_id:str, request:Request):
        job = get_job_or_404(job_id)

        async def stream():
            last_version = -1
            quiet_ticks = 0
            while True:
                if await request.is_disconnected():
                    break
                version = job.version
                if version != last_version:
                    last_version = version
                    quiet_ticks = 0
                    snap = job.snapshot()
                    yield f"data: {json.dumps(snap)}\n\n"
                    if snap["status"] in FINISHED_STATES:
                        break
                else:
                    quiet_ticks += 1
                    if quiet_ticks % 60 ==0:
                        yield ": keepalive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event_stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app

app = create_app()