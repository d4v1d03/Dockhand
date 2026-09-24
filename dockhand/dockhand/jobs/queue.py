def enqueue_run(session_id: str) -> None:
    from dockhand.worker import celery_app

    celery_app.send_task("dockhand.run_session", args=[session_id])
