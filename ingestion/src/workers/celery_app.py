"""
Shared Celery application instance for all ingestion worker tasks.

Structure note: this module defines `celery_app` first, then imports
batch_worker and scheduled_tasks at the BOTTOM of the file so Celery
registers every @celery_app.task-decorated function when the app is
loaded (worker: `-A src.workers.celery_app.celery_app`, beat: same path
+ `beat`). batch_worker.py and scheduled_tasks.py both do
`from .celery_app import celery_app` at their own top — this looks
circular but works: by the time this file's bottom-of-file import
statement runs, `celery_app` is already bound in this module's namespace,
so the back-reference resolves fine. This is a standard, if slightly
eyebrow-raising, Celery project layout — do not "fix" the import order,
it will actually break it.

Decision (per your instruction): Celery beat ships now, not deferred to
Phase 10. Scope is intentionally narrower than the original doc 34
design — 'rebuild-bm25' is NOT scheduled here, because BM25/hybrid
retrieval doesn't exist until the RAG engine lands in Phase 7. Add it to
beat_schedule at that point; scheduling it against a task that isn't
registered yet just logs "Received unregistered task" every tick.
"""
from celery import Celery
from celery.schedules import crontab

from ..config import settings

celery_app = Celery("pvh-ingestion", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,            # ack only after the task actually completes
    worker_prefetch_multiplier=1,   # one task at a time per worker process
    task_track_started=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-old-ingestion-jobs": {
        "task": "pvh.cleanup_completed_jobs",
        "schedule": crontab(hour="2", minute="0"),   # 2am daily
    },
    "requeue-stale-processing-documents": {
        "task": "pvh.requeue_stale_documents",
        "schedule": crontab(minute="*/15"),
    },
}

# Import task-defining modules for their side effect of registering
# @celery_app.task functions — see the module docstring above.
from . import batch_worker, scheduled_tasks  # noqa: E402, F401
