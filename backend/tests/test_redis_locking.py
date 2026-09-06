import pytest
import asyncio
from services.lock_service import (
    acquire_slot_lock,
    verify_slot_lock,
    release_slot_lock,
    get_slot_lock_status,
    force_release_slot_lock,
)


@pytest.mark.asyncio
async def test_redis_slot_lock_lifecycle():
    doc_id = "doc_redis_test_1"
    date = "2026-11-30"
    time_slot = "09:30"
    user_a = "user_patient_a"
    user_b = "user_patient_b"

    await force_release_slot_lock(doc_id, date, time_slot)

    # 1. User A acquires lock
    ok, token_a, ttl, msg = await acquire_slot_lock(
        doctor_id=doc_id,
        date=date,
        time_slot=time_slot,
        user_id=user_a,
        ttl_seconds=300
    )
    assert ok is True
    assert token_a is not None
    assert ttl > 0

    # 2. User B tries to acquire lock on the SAME slot -> Fails (409 Conflict logic)
    ok_b, token_b, ttl_b, msg_b = await acquire_slot_lock(
        doctor_id=doc_id,
        date=date,
        time_slot=time_slot,
        user_id=user_b,
        ttl_seconds=300
    )
    assert ok_b is False
    assert token_b is None

    # 3. Status checks
    is_locked, held_by_a, _ = await get_slot_lock_status(doc_id, date, time_slot, current_user_id=user_a)
    assert is_locked is True
    assert held_by_a is True

    _, held_by_b, _ = await get_slot_lock_status(doc_id, date, time_slot, current_user_id=user_b)
    assert held_by_b is False

    # 4. User B cannot release User A's lock
    released_by_b = await release_slot_lock(doc_id, date, time_slot, user_b, "fake_token")
    assert released_by_b is False

    # 5. User A releases lock safely
    released_by_a = await release_slot_lock(doc_id, date, time_slot, user_a, token_a)
    assert released_by_a is True

    # 6. Now User B can acquire the slot
    ok_b2, token_b2, _, _ = await acquire_slot_lock(
        doctor_id=doc_id,
        date=date,
        time_slot=time_slot,
        user_id=user_b,
        ttl_seconds=300
    )
    assert ok_b2 is True
    assert token_b2 is not None

    # Clean up
    await force_release_slot_lock(doc_id, date, time_slot)
