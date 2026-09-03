import json
import logging
import secrets
import time
from typing import Optional, Tuple
from config import SLOT_LOCK_TTL_SECONDS
from redis_client import get_redis, get_memory_lock_store

logger = logging.getLogger("medibook.lock_service")

# Lua script to release lock atomically ONLY if the token matches
RELEASE_LOCK_LUA_SCRIPT = """
local val = redis.call('get', KEYS[1])
if not val then
    return 0
end
local decoded = cjson.decode(val)
if decoded.token == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _get_slot_lock_key(doctor_id: str, date: str, time_slot: str) -> str:
    # Normalize inputs to prevent key mismatches
    clean_doctor_id = str(doctor_id).strip()
    clean_date = str(date).strip()
    clean_time = str(time_slot).strip().upper()
    return f"medibook:lock:slot:{clean_doctor_id}:{clean_date}:{clean_time}"


async def acquire_slot_lock(
    doctor_id: str,
    date: str,
    time_slot: str,
    user_id: str,
    ttl_seconds: int = SLOT_LOCK_TTL_SECONDS
) -> Tuple[bool, Optional[str], Optional[int], str]:
    """
    Acquire an atomic distributed lock on a doctor's slot for a specified duration.
    Returns: (success: bool, lock_token: Optional[str], expires_in_seconds: Optional[int], message: str)
    """
    key = _get_slot_lock_key(doctor_id, date, time_slot)
    token = secrets.token_hex(16)
    payload = {
        "user_id": str(user_id),
        "token": token,
        "doctor_id": str(doctor_id),
        "date": date,
        "time": time_slot,
        "created_at": time.time(),
    }
    payload_str = json.dumps(payload)

    redis = await get_redis()
    if redis is not None:
        try:
            # Atomic SET NX EX
            acquired = await redis.set(key, payload_str, nx=True, ex=ttl_seconds)
            if acquired:
                return True, token, ttl_seconds, "Slot locked successfully"

            # Check if current user already holds the active lock
            current_raw = await redis.get(key)
            if current_raw:
                try:
                    data = json.loads(current_raw)
                    if data.get("user_id") == str(user_id):
                        ttl = await redis.ttl(key)
                        return True, data.get("token"), max(0, ttl), "Slot already locked by you"
                    else:
                        ttl = await redis.ttl(key)
                        return False, None, max(0, ttl), "Slot is currently on hold by another user"
                except Exception:
                    pass
            return False, None, None, "Slot is currently unavailable"
        except Exception as e:
            logger.warning(f"Redis error during acquire_slot_lock: {e}. Falling back to memory lock store.")

    # Fallback in-memory
    mem_store = get_memory_lock_store()
    acquired = await mem_store.set_nx(key, payload_str, ttl_seconds)
    if acquired:
        return True, token, ttl_seconds, "Slot locked successfully (in-memory)"

    current_raw = await mem_store.get(key)
    if current_raw:
        try:
            data = json.loads(current_raw)
            if data.get("user_id") == str(user_id):
                ttl = await mem_store.ttl(key)
                return True, data.get("token"), max(0, ttl), "Slot already locked by you"
            else:
                ttl = await mem_store.ttl(key)
                return False, None, max(0, ttl), "Slot is currently on hold by another user"
        except Exception:
            pass
    return False, None, None, "Slot is currently locked"


async def verify_slot_lock(
    doctor_id: str,
    date: str,
    time_slot: str,
    user_id: str,
    lock_token: Optional[str]
) -> bool:
    """
    Verifies whether the given user holds the active lock for the slot with the matching lock_token.
    If no lock is held or token is invalid, returns False.
    """
    if not lock_token:
        return False

    key = _get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()

    if redis is not None:
        try:
            raw = await redis.get(key)
            if not raw:
                return False
            data = json.loads(raw)
            return (
                str(data.get("user_id")) == str(user_id)
                and data.get("token") == lock_token
            )
        except Exception as e:
            logger.warning(f"Redis error during verify_slot_lock: {e}")

    mem_store = get_memory_lock_store()
    raw = await mem_store.get(key)
    if not raw:
        return False
    try:
        data = json.loads(raw)
        return (
            str(data.get("user_id")) == str(user_id)
            and data.get("token") == lock_token
        )
    except Exception:
        return False


async def release_slot_lock(
    doctor_id: str,
    date: str,
    time_slot: str,
    user_id: str,
    lock_token: str
) -> bool:
    """
    Safely releases the distributed slot lock only if the token and user match.
    """
    key = _get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()

    if redis is not None:
        try:
            res = await redis.eval(RELEASE_LOCK_LUA_SCRIPT, 1, key, lock_token)
            return bool(res)
        except Exception as e:
            logger.warning(f"Redis error during release_slot_lock: {e}")

    mem_store = get_memory_lock_store()
    raw = await mem_store.get(key)
    if not raw:
        return False
    try:
        data = json.loads(raw)
        if str(data.get("user_id")) == str(user_id) and data.get("token") == lock_token:
            await mem_store.delete(key)
            return True
    except Exception:
        pass
    return False


async def get_slot_lock_status(
    doctor_id: str,
    date: str,
    time_slot: str,
    current_user_id: Optional[str] = None
) -> Tuple[bool, bool, Optional[int]]:
    """
    Returns: (is_locked: bool, held_by_current_user: bool, remaining_ttl_seconds: Optional[int])
    """
    key = _get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()

    if redis is not None:
        try:
            raw = await redis.get(key)
            if not raw:
                return False, False, None
            ttl = await redis.ttl(key)
            data = json.loads(raw)
            held_by_current = (
                current_user_id is not None
                and str(data.get("user_id")) == str(current_user_id)
            )
            return True, held_by_current, max(0, ttl) if ttl > 0 else None
        except Exception as e:
            logger.warning(f"Redis error during get_slot_lock_status: {e}")

    mem_store = get_memory_lock_store()
    raw = await mem_store.get(key)
    if not raw:
        return False, False, None
    try:
        data = json.loads(raw)
        ttl = await mem_store.ttl(key)
        held_by_current = (
            current_user_id is not None
            and str(data.get("user_id")) == str(current_user_id)
        )
        return True, held_by_current, max(0, ttl) if ttl > 0 else None
    except Exception:
        return False, False, None


async def force_release_slot_lock(doctor_id: str, date: str, time_slot: str) -> bool:
    """
    Force release a slot lock (admin / system cleanup).
    """
    key = _get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()
    if redis is not None:
        try:
            res = await redis.delete(key)
            return bool(res)
        except Exception as e:
            logger.warning(f"Redis error during force_release_slot_lock: {e}")

    mem_store = get_memory_lock_store()
    return await mem_store.delete(key)
