from celery import Celery

from docagent.config import settings

config = settings()
if config.job_backend != "celery" or config.redis_backend != "real":
    raise RuntimeError("Celery workers require DOCAGENT_JOB_BACKEND=celery and DOCAGENT_REDIS_BACKEND=real")

celery = Celery("docagent", broker=config.redis_url, backend=config.redis_url)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_soft_time_limit=6800,
    task_time_limit=7200,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "retention-cleanup": {"task": "docagent.cleanup", "schedule": 86400},
        "recover-jobs": {"task": "docagent.recover", "schedule": 60},
    },
)


@celery.task(name="docagent.analyze")
def analyze_task(job_id):
    from docagent.jobs import run_job

    run_job(job_id)


@celery.task(name="docagent.cleanup")
def cleanup_task():
    from docagent.jobs import cleanup

    return cleanup()


@celery.task(name="docagent.recover")
def recover_task():
    from docagent.jobs import recover_jobs

    return recover_jobs()
