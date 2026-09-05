import logging
from celery_app import celery_app, run_async
from redis_client import get_redis, get_memory_lock_store

logger = logging.getLogger("medibook.tasks.cleanup")


async def _async_cleanup_slot_locks():
    """Cleans up any dangling in-memory expired locks."""
    mem_store = get_memory_lock_store()
    count = 0
    # The in-memory store self-evicts on ttl/get, this ensures active sweeping
    now = mem_store._store.copy() if hasattr(mem_store, "_store") else {}
    for k in list(now.keys()):
        ttl = await mem_store.ttl(k)
        if ttl <= 0:
            await mem_store.delete(k)
            count += 1
    logger.info(f"Cleaned up {count} expired in-memory slot locks.")
    return {"cleaned": count}


@celery_app.task(name="tasks.cleanup_tasks.cleanup_slot_locks_task")
def cleanup_slot_locks_task():
    return run_async(_async_cleanup_slot_locks())
