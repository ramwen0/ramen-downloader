"""Tests for the web API. Run with:  pytest

A FakeDownloader stands in for the real engine, so no YouTube, no ffmpeg:
we script exactly what it reports and check what the API tells the client.
"""
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ramen_downloader.core import (Finished, PlaylistFound, TrackDone,  # noqa: E402
                                   TrackFailed, TrackProgress)
from ramen_downloader.jobs import JobManager  # noqa: E402
from ramen_downloader.server import create_app  # noqa: E402

GOOD_URL = "https://www.youtube.com/playlist?list=abc"


class FakeDownloader:
    """Reports a fixed script: track 1 ok, track 2 fails."""

    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def download_playlist(self, url, out_dir, on_event):
        on_event(PlaylistFound("Mix", 2))
        on_event(TrackProgress(1, 2, "Song A", 50.0, 25.0))
        on_event(TrackDone(1, 2, "Song A"))
        on_event(TrackFailed(2, 2, "Song B", "boom"))
        on_event(Finished(cancelled=False, succeeded=1, failed=1))


class BlockingDownloader(FakeDownloader):
    """Starts, then waits until cancelled (to test cancel and queueing)."""

    def download_playlist(self, url, out_dir, on_event):
        on_event(PlaylistFound("Mix", 5))
        self._cancel.wait(timeout=5)
        on_event(Finished(cancelled=self._cancel.is_set(), succeeded=0, failed=0))


def make_client(tmp_path, factory=FakeDownloader, max_concurrent=1):
    manager = JobManager(str(tmp_path), downloader_factory=factory, max_concurrent=max_concurrent)
    return TestClient(create_app(manager))


def wait_for(client, job_id, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/api/jobs/{job_id}").json()
        if predicate(snap):
            return snap
        time.sleep(0.02)
    raise AssertionError(f"timed out; last state: {snap}")


def test_create_job_and_watch_it_finish(tmp_path):
    client = make_client(tmp_path)
    resp = client.post("/api/jobs", json={"url": GOOD_URL})
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    snap = wait_for(client, job_id, lambda s: s["status"] == "done")
    assert snap["playlist_title"] == "Mix"
    assert snap["total"] == 2
    assert (snap["succeeded"], snap["failed"]) == (1, 1)
    assert snap["overall_percent"] == 100.0
    assert [t["status"] for t in snap["tracks"]] == ["done", "failed"]
    assert snap["tracks"][1]["error"] == "boom"


@pytest.mark.parametrize("bad_url", [
    "not a url",
    "ftp://youtube.com/x",
    "https://evil.example.com/watch?v=1",
    "http://127.0.0.1:8080/secret",          # internal address: must be refused
    "https://youtube.com.evil.example/x",    # look-alike host
])
def test_rejects_bad_urls(tmp_path, bad_url):
    client = make_client(tmp_path)
    assert client.post("/api/jobs", json={"url": bad_url}).status_code == 422


def test_unknown_job_is_404(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.get("/api/jobs/nope/events").status_code == 404


def test_list_jobs_newest_first(tmp_path):
    client = make_client(tmp_path)
    first = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    time.sleep(0.01)
    second = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert ids == [second, first]


def test_cancel_running_job(tmp_path):
    client = make_client(tmp_path, factory=BlockingDownloader)
    job_id = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    wait_for(client, job_id, lambda s: s["status"] == "running")

    client.post(f"/api/jobs/{job_id}/cancel")
    snap = wait_for(client, job_id, lambda s: s["status"] == "cancelled")
    assert snap["status"] == "cancelled"


def test_cancel_queued_job_never_starts(tmp_path):
    client = make_client(tmp_path, factory=BlockingDownloader, max_concurrent=1)
    first = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    wait_for(client, first, lambda s: s["status"] == "running")
    second = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]

    # Only one slot, so the second job must be waiting.
    assert client.get(f"/api/jobs/{second}").json()["status"] == "queued"

    client.post(f"/api/jobs/{second}/cancel")
    assert client.get(f"/api/jobs/{second}").json()["status"] == "cancelled"

    client.post(f"/api/jobs/{first}/cancel")    # let the first one end
    wait_for(client, first, lambda s: s["status"] == "cancelled")
    # The cancelled-while-queued job must still be cancelled, not resurrected.
    time.sleep(0.1)
    snap = client.get(f"/api/jobs/{second}").json()
    assert snap["status"] == "cancelled" and snap["playlist_title"] is None


def test_event_stream_sends_final_state_then_closes(tmp_path):
    client = make_client(tmp_path)
    job_id = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    wait_for(client, job_id, lambda s: s["status"] == "done")

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        data_lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    assert len(data_lines) == 1                       # already finished -> one message, then closes
    final = json.loads(data_lines[0][len("data: "):])
    assert final["status"] == "done" and final["succeeded"] == 1


def test_event_stream_follows_a_live_job(tmp_path):
    client = make_client(tmp_path, factory=BlockingDownloader)
    job_id = client.post("/api/jobs", json={"url": GOOD_URL}).json()["id"]
    wait_for(client, job_id, lambda s: s["status"] == "running")

    threading.Timer(0.3, lambda: client.post(f"/api/jobs/{job_id}/cancel")).start()

    statuses = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                statuses.append(json.loads(line[6:])["status"])

    assert statuses[0] == "running" and statuses[-1] == "cancelled"