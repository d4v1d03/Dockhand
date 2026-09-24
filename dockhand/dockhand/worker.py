import socket

from celery import Celery

from dockhand.config import get_settings

settings = get_settings()

celery_app = Celery("dockhand", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # long-running tasks: ack after completion, one at a time per worker
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    # a redelivered message must not be re-run while a copy is still executing
    broker_transport_options={"visibility_timeout": 6 * 3600},
    # periodic housekeeping; run `celery -A dockhand.worker beat` (or worker -B)
    beat_schedule={
        "maintenance": {
            "task": "dockhand.maintenance",
            "schedule": settings.maintenance_interval_s,
        },
    },
    task_routes={"dockhand.maintenance": {"queue": "maintenance"}},
    task_default_queue="runs",
)


@celery_app.task(name="dockhand.ping")
def ping(message: str = "pong") -> dict:
    return {"message": message, "worker": socket.gethostname()}


@celery_app.task(name="dockhand.run_session")
def run_session(session_id: str) -> str:
    from dockhand.db.engine import init_db
    from dockhand.jobs.runner import run_session as _run

    init_db()
    return _run(session_id)


@celery_app.task(name="dockhand.maintenance")
def maintenance() -> dict:
    from dockhand.db.engine import init_db
    from dockhand.jobs.maintenance import reap, sweep_stuck_sessions

    init_db()
    return {"reaped": reap(), "rescued": sweep_stuck_sessions()}
