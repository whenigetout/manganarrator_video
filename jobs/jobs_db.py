# jobs_db.py
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
import uuid
import json
from typing import Optional
from app.models.domain import JobStatus, JobType, JobResponse, JobStatus, JobResult

DB_PATH = Path(__file__).parent / "jobs.db"

def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)

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

def create_job(job_type: JobType = JobType.build_image):
    job_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO jobs (job_id, status, created_at)
        VALUES (?, ?, ?)
        """, (
            job_id,
            JobStatus.processing.value,
            datetime.utcnow().isoformat()
        ))
    return job_id


def update_job(job_id: str, status: JobStatus, result=None, error: str | None = None):
    with get_conn() as conn:
        conn.execute("""
        UPDATE jobs
        SET status = ?, result = ?, error = ?
        WHERE job_id = ?
        """, (
            status.value,
            json.dumps(result) if result else None,
            error,
            job_id
        ))

def get_job(job_id: str) -> Optional[JobResponse]:
    with get_conn() as conn:
        row = conn.execute("""
        SELECT job_id, status, result, error
        FROM jobs WHERE job_id = ?
        """, (job_id,)).fetchone()

    if not row:
        return None

    return JobResponse(
        job_id=row[0],
        status=JobStatus(row[1]),
        result=JobResult(**json.loads(row[2])) if row[2] else None,
        error=row[3]
    )
