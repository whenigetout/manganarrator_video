from functools import wraps
import threading
from jobs.jobs_db import create_job, update_job
from app.models.domain import JobStatus, JobType

def async_job(job_type: JobType):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            job_id = create_job(job_type)

            def run():
                try:
                    result = fn(*args, **kwargs)

                    update_job(job_id, JobStatus.done, result={
                        "type": job_type.value,
                        "data": result
                    })

                except Exception as e:
                    update_job(job_id, JobStatus.failed, error=str(e))

            threading.Thread(target=run).start()

            return {
                "status": "processing",
                "job_id": job_id
            }

        return wrapper
    return decorator