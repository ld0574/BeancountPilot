"""
In-memory progress store for long-running jobs.
"""

import threading
import time
import uuid
from typing import Any, Dict, Optional

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def create_job(total: int) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "total": int(total),
            "done": 0,
            "error": "",
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    return job_id


def increment(job_id: str, inc: int = 1) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["done"] = min(job["total"], job["done"] + int(inc))
        job["updated_at"] = time.time()


def set_meta(job_id: str, **meta: Any) -> None:
    """Update arbitrary metadata fields for a job."""
    if not meta:
        return
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.update(meta)
        job["updated_at"] = time.time()


def set_result(job_id: str, result: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["result"] = result
        job["status"] = "done"
        job["done"] = job["total"]
        job["updated_at"] = time.time()


def set_error(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "error"
        job["error"] = error
        job["updated_at"] = time.time()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return dict(job)
