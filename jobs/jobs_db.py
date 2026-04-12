# jobs_db.py
import sqlite3
from pathlib import Path
from datetime import datetime
import threading

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

import uuid
import json

def create_job():
    job_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO jobs (job_id, status, created_at)
        VALUES (?, ?, ?)
        """, (job_id, "processing", datetime.utcnow().isoformat()))
    return job_id


def update_job(job_id, status, result=None, error=None):
    with get_conn() as conn:
        conn.execute("""
        UPDATE jobs
        SET status = ?, result = ?, error = ?
        WHERE job_id = ?
        """, (
            status,
            json.dumps(result) if result else None,
            error,
            job_id
        ))


def get_job(job_id):
    with get_conn() as conn:
        row = conn.execute("""
        SELECT job_id, status, result, error
        FROM jobs WHERE job_id = ?
        """, (job_id,)).fetchone()

    if not row:
        return None

    return {
        "job_id": row[0],
        "status": row[1],
        "result": json.loads(row[2]) if row[2] else None,
        "error": row[3]
    }

def run_async_job(fn):
    job_id = create_job()

    def wrapper():
        try:
            result = fn()
            update_job(job_id, "done", result=result)
        except Exception as e:
            update_job(job_id, "failed", error=str(e))

    threading.Thread(target=wrapper).start()

    return job_id