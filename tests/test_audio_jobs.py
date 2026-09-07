import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.domain import JobStatus, JobType
from jobs import jobs_db as db


class AudioJobTests(unittest.TestCase):
    def test_legacy_migration_and_audio_progress(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(db, "DB_PATH", Path(folder) / "jobs.db"):
            with sqlite3.connect(db.DB_PATH) as conn:
                conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, status TEXT, result TEXT, error TEXT, created_at TEXT)")
                conn.execute("INSERT INTO jobs VALUES ('old', 'done', ?, NULL, '2025')",
                             (json.dumps({"type": "build_image", "data": {"namespace": "outputs", "path": "old.mp4"}}),))
            conn.close()
            db.init_db()
            db.init_db()
            self.assertEqual(db.get_job("old").result.type, JobType.build_image)
            self.assertEqual(db.get_job("old").progress, 100)
            audio = db.create_job(JobType.build_audio_video)
            manga = db.create_job(JobType.build_image)
            db.update_progress(audio, 42, "Rendering spectrum")
            self.assertEqual(db.get_job(audio).progress, 42)
            self.assertEqual([job.job_id for job in db.list_audio_jobs()], [audio])
            db.mark_interrupted_audio_jobs()
            self.assertEqual(db.get_job(audio).status, JobStatus.failed)
            self.assertEqual(db.get_job(audio).stage, "Interrupted")
            self.assertEqual(db.get_job(manga).status, JobStatus.processing)


if __name__ == "__main__":
    unittest.main()
