"""Celery app and tasks."""

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
    beat_schedule={},
)


@celery_app.task(name="dockhand.ping")
def ping(message: str = "pong") -> dict:
    return {"message": message, "worker": socket.gethostname()}
