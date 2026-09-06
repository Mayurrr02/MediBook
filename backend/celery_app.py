import os
import asyncio
from celery import Celery
from celery.schedules import crontab
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery(
    "medibook_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "tasks.reminders",
        "tasks.waitlist_tasks",
        "tasks.cleanup_tasks",
    ],
)
app = celery_app
celery = celery_app

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "send-24h-reminders-every-morning": {
            "task": "tasks.reminders.send_24h_reminders_task",
            "schedule": crontab(hour=8, minute=0),  # 8:00 AM UTC daily
        },
        "send-1h-reminders-every-15-min": {
            "task": "tasks.reminders.send_1h_reminders_task",
            "schedule": crontab(minute="*/15"),
        },
        "expire-stale-waitlists-every-minute": {
            "task": "tasks.waitlist_tasks.expire_stale_waitlists_task",
            "schedule": crontab(minute="*"),
        },
        "cleanup-slot-locks-every-5-min": {
            "task": "tasks.cleanup_tasks.cleanup_slot_locks_task",
            "schedule": crontab(minute="*/5"),
        },
    },
)


def run_async(coro):
    """Helper to run async coroutines safely from sync Celery task worker."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)
