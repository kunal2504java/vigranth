"""
Celery application for background task processing.

Tasks:
  - Platform message sync (every 2 minutes)
  - Snoozed message checks (every 1 minute)
"""
from celery import Celery
from backend.core.config import get_settings

settings = get_settings()

celery = Celery(
    "unifyinbox",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,

    # Result expiry
    result_expires=3600,

    # Retry policy
    task_default_retry_delay=30,
    task_max_retries=5,

    # Beat schedule — periodic background jobs
    beat_schedule={
        "sync-all-platforms": {
            "task": "backend.tasks.sync.sync_all_users",
            "schedule": settings.PLATFORM_SYNC_INTERVAL_SECONDS,
        },
        "check-snoozed-messages": {
            "task": "backend.tasks.sync.check_snoozed_messages",
            "schedule": settings.SNOOZE_CHECK_INTERVAL_SECONDS,
        },
    },
)

# Explicitly include task modules (autodiscover looks for tasks.py, ours is sync.py)
celery.conf.include = ["backend.tasks.sync"]
