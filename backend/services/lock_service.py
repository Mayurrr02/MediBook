import json
import logging
import secrets
import time
from typing import Optional, Tuple
from config import SLOT_LOCK_TTL_SECONDS
from redis_client import get_redis, get_memory_lock_store

logger = logging.getLogger("medibook.lock_service")

# Atomic release script: only deletes if the token in the stored JSON matches ARGV[1]
RELEASE_LOCK_LUA_SCRIPT = """
local val = redis.call('get', KEYS[1])
if not val then
    return 0
end
local ok, decoded = pcall(cjson.decode, val)
if ok and decoded.token == ARGV[1] then
    return redis.call('del', KEYS[1])
elseif val == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def get_slot_lock_key(doctor_id: str, date: str, time_slot: str) -> str:
    """Format: appointment_lock:{doctor_id}:{date}:{time}"""
    clean_doctor_id = str(doctor_id).strip()
    clean_date = str(date).strip()
    clean_time = str(time_slot).strip().upper()
    return f"appointment_lock:{clean_doctor_id}:{clean_date}:{clean_time}"


async def acquire_slot_lock(
    doctor_id: str,
    date: str,
    time_slot: str,
    user_id: str,
    ttl_seconds: int = SLOT_LOCK_TTL_SECONDS
) -> Tuple[bool, Optional[str], Optional[int], str]:
    """
    Acquires an atomic distributed lock on an appointment slot.
    Returns: (success: bool, lock_token: Optional[str], expires_in_seconds: Optional[int], message: str)
    """
    key = get_slot_lock_key(doctor_id, date, time_slot)
    token = secrets.token_hex(16)
    payload = {
        "user_id": str(user_id),
        "token": token,
        "doctor_id": str(doctor_id),
        "date": date,
        "time": time_slot,
        "created_at": time.time(),
        "ttl": ttl_seconds,
    }
    payload_str = json.dumps(payload)

    redis = await get_redis()
    if redis is not None:
        try:
            # Atomic SET NX EX
            acquired = await redis.set(key, payload_str, nx=True, ex=ttl_seconds)
            if acquired:
                return True, token, ttl_seconds, "Slot hold acquired successfully."

            # If already locked, check if held by the exact same user
            current_raw = await redis.get(key)
            if current_raw:
                try:
                    data = json.loads(current_raw)
                    if data.get("user_id") == str(user_id):
                        ttl = await redis.ttl(key)
                        return True, data.get("token"), max(0, ttl), "Slot already held by you."
                    else:
                        ttl = await redis.ttl(key)
                        return False, None, max(0, ttl), "Slot is currently on hold by another patient."
                except Exception:
                    pass
            return False, None, None, "Slot is currently locked."
        except Exception as e:
            logger.warning(f"Redis error in acquire_slot_lock: {e}. Using memory lock store.")

    # In-memory fallback
    mem_store = get_memory_lock_store()
    acquired = await mem_store.set_nx(key, payload_str, ttl_seconds)
    if acquired:
        return True, token, ttl_seconds, "Slot hold acquired successfully (in-memory)."

    current_raw = await mem_store.get(key)
    if current_raw:
        try:
            data = json.loads(current_raw)
            if data.get("user_id") == str(user_id):
                ttl = await mem_store.ttl(key)
                return True, data.get("token"), max(0, ttl), "Slot already held by you."
            else:
                ttl = await mem_store.ttl(key)
                return False, None, max(0, ttl), "Slot is currently on hold by another patient."
        except Exception:
            pass

    return False, None, None, "Slot is currently locked."


async def verify_slot_lock(
    doctor_id: str,
    date: str,
    time_slot: str,
    user_id: str,
    lock_token: Optional[str]
) -> bool:
    """
    Verifies that the lock is active, belongs to user_id, and matches lock_token.
    """
    if not lock_token:
        return False

    key = get_slot_lock_key(doctor_id, date, time_slot)
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
            logger.warning(f"Redis error in verify_slot_lock: {e}")

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
    Safely releases the distributed lock only if token and user match.
    """
    key = get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()

    if redis is not None:
        try:
            res = await redis.eval(RELEASE_LOCK_LUA_SCRIPT, 1, key, lock_token)
            return bool(res)
        except Exception as e:
            logger.warning(f"Redis error in release_slot_lock: {e}")

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
    Returns: (is_locked: bool, is_held_by_current_user: bool, remaining_ttl_seconds: Optional[int])
    """
    key = get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()

    if redis is not None:
        try:
            raw = await redis.get(key)
            if not raw:
                return False, False, None
            ttl = await redis.ttl(key)
            data = json.loads(raw)
            held_by_me = (
                current_user_id is not None
                and str(data.get("user_id")) == str(current_user_id)
            )
            return True, held_by_me, max(0, ttl) if ttl > 0 else None
        except Exception as e:
            logger.warning(f"Redis error in get_slot_lock_status: {e}")

    mem_store = get_memory_lock_store()
    raw = await mem_store.get(key)
    if not raw:
        return False, False, None
    try:
        data = json.loads(raw)
        ttl = await mem_store.ttl(key)
        held_by_me = (
            current_user_id is not None
            and str(data.get("user_id")) == str(current_user_id)
        )
        return True, held_by_me, max(0, ttl) if ttl > 0 else None
    except Exception:
        return False, False, None


async def force_release_slot_lock(doctor_id: str, date: str, time_slot: str) -> bool:
    """
    Administrative / system cleanup to force release a lock.
    """
    key = get_slot_lock_key(doctor_id, date, time_slot)
    redis = await get_redis()
    if redis is not None:
        try:
            res = await redis.delete(key)
            return bool(res)
        except Exception as e:
            logger.warning(f"Redis error in force_release_slot_lock: {e}")

    mem_store = get_memory_lock_store()
    return await mem_store.delete(key)
