import logging
from celery_app import celery_app, run_async
from services.waitlist_service import expire_stale_waitlist_claims

logger = logging.getLogger("medibook.tasks.waitlist")


@celery_app.task(name="tasks.waitlist_tasks.expire_stale_waitlists_task")
def expire_stale_waitlists_task():
    logger.info("Running expire_stale_waitlists_task...")
    return run_async(expire_stale_waitlist_claims())
