# jobs_db.py
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
import uuid
import json
from contextlib import contextmanager
from typing import Optional
from app.models.domain import JobStatus, JobType, JobResponse, JobStatus, JobResult

DB_PATH = Path(__file__).parent / "jobs.db"

@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT,
            result TEXT,
            error TEXT,
            created_at TEXT
        )
        """)

        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        for name, definition in (("progress", "REAL DEFAULT 0"), ("stage", "TEXT"), ("job_type", "TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")

def create_job(job_type: JobType = JobType.build_image):
    job_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO jobs (job_id, status, created_at, job_type, stage)
        VALUES (?, ?, ?, ?, ?)
        """, (
            job_id,
            JobStatus.processing.value,
            datetime.utcnow().isoformat(),
            job_type.value,
            "Queued"
        ))
    return job_id


def _json_default(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, Path):
        return str(value)
    return str(value)

def update_job(job_id: str, status: JobStatus, result=None, error: str | None = None):
    with get_conn() as conn:
        conn.execute("""
        UPDATE jobs
        SET status = ?, result = ?, error = ?
        WHERE job_id = ?
        """, (
            status.value,
            json.dumps(result, default=_json_default) if result else None,
            error,
            job_id
        ))

def get_job(job_id: str) -> Optional[JobResponse]:
    with get_conn() as conn:
        row = conn.execute("""
        SELECT job_id, status, result, error, progress, stage
        FROM jobs WHERE job_id = ?
        """, (job_id,)).fetchone()

    if not row:
        return None

    return JobResponse(
        job_id=row[0],
        status=JobStatus(row[1]),
        result=JobResult(**json.loads(row[2])) if row[2] else None,
        error=row[3],
        progress=100 if row[1] == "done" else (row[4] or 0),
        stage=row[5]
    )


def update_progress(job_id, progress, stage):
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET progress = ?, stage = ? WHERE job_id = ?", (progress, stage, job_id))


def list_audio_jobs(limit=30):
    with get_conn() as conn:
        rows = conn.execute("SELECT job_id FROM jobs WHERE job_type = ? ORDER BY created_at DESC LIMIT ?",
                            (JobType.build_audio_video.value, limit)).fetchall()
    return [get_job(row[0]) for row in rows]


def mark_interrupted_audio_jobs():
    with get_conn() as conn:
        conn.execute("""UPDATE jobs SET status = ?, stage = ?, error = ?
                        WHERE job_type = ? AND status = ?""",
                     (JobStatus.failed.value, "Interrupted", "Backend restarted before this render finished. Submit it again.",
                      JobType.build_audio_video.value, JobStatus.processing.value))
