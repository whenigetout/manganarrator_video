from functools import wraps
import threading
from jobs.jobs_db import create_job, update_job


def async_job(job_type="generic"):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            job_id = create_job()

            def run():
                try:
                    result = fn(*args, **kwargs)

                    update_job(job_id, "done", result={
                        "type": job_type,
                        "data": result
                    })

                except Exception as e:
                    update_job(job_id, "failed", error=str(e))

            threading.Thread(target=run).start()

            return {
                "status": "processing",
                "job_id": job_id
            }

        return wrapper
    return decorator