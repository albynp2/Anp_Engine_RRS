"""Job manager ringan: 1 job aktif pada satu waktu, progres via SSE."""
import json
import threading
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional


class BusyError(Exception):
    pass


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, type_: str, params: dict):
        self.id = uuid.uuid4().hex[:12]
        self.type = type_
        self.params = params
        self.status = "queued"
        self.progress = 0
        self.stage = "Menunggu"
        self.result: Any = None
        self.error: Optional[str] = None
        self.events: List[dict] = []
        self.cancel_flag = False
        self._lock = threading.Lock()
        self.started = time.time()

    # --- API untuk fungsi job ---
    def _push(self, evt: dict):
        with self._lock:
            self.events.append(evt)

    def set_progress(self, percent: float, stage: str = ""):
        self.progress = max(0, min(100, round(percent, 1)))
        if stage:
            self.stage = stage
        self._push({"type": "progress", "percent": self.progress, "stage": self.stage})

    def log(self, message: str, level: str = "info"):
        self._push({"type": "log", "level": level, "message": str(message)})

    def check_cancel(self):
        if self.cancel_flag:
            raise Cancelled()

    # --- dibaca oleh API ---
    @property
    def finished(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    def events_since(self, idx: int):
        with self._lock:
            return self.events[idx:], len(self.events)

    def public(self) -> dict:
        return {"id": self.id, "type": self.type, "status": self.status,
                "progress": self.progress, "stage": self.stage,
                "result": self.result, "error": self.error}


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def active(self) -> Optional[Job]:
        with self._lock:
            for j in self.jobs.values():
                if not j.finished:
                    return j
        return None

    def start(self, type_: str, fn: Callable[[Job, dict], Any], params: dict) -> Job:
        with self._lock:
            for j in self.jobs.values():
                if not j.finished:
                    raise BusyError(f"Masih ada proses berjalan: {j.type} ({j.stage})")
            job = Job(type_, params)
            self.jobs[job.id] = job
            # simpan 20 job terakhir saja
            if len(self.jobs) > 20:
                for k in [k for k, v in self.jobs.items() if v.finished][:len(self.jobs) - 20]:
                    self.jobs.pop(k, None)
        threading.Thread(target=self._run, args=(job, fn), daemon=True).start()
        return job

    def _run(self, job: Job, fn):
        job.status = "running"
        job.set_progress(1, "Mulai")
        try:
            job.result = fn(job, job.params)
            job.status = "completed"
            job.set_progress(100, "Selesai")
        except Cancelled:
            job.status = "cancelled"
            job.stage = "Dibatalkan"
        except Exception as e:  # noqa
            job.status = "failed"
            job.error = str(e) or e.__class__.__name__
            job._push({"type": "error", "message": job.error,
                       "traceback": traceback.format_exc()[-3000:]})
        finally:
            job._push({"type": "complete", "status": job.status, "progress": job.progress,
                       "result": job.result, "error": job.error})

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)


def sse_stream(job: Job):
    """Generator SSE. Dipanggil dari StreamingResponse (dijalankan di threadpool)."""
    idx = 0
    idle = 0
    while True:
        evts, idx = job.events_since(idx)
        for e in evts:
            yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
        if job.finished and not evts:
            break
        idle = 0 if evts else idle + 1
        if idle and idle % 40 == 0:
            yield ": ping\n\n"
        time.sleep(0.4)


manager = JobManager()
