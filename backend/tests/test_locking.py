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
async def test_acquire_and_release_lock():
    doctor_id = "doc_test_123"
    date = "2026-10-15"
    time_slot = "10:00 AM"
    user_id = "user_abc_456"

    # Clean previous locks
    await force_release_slot_lock(doctor_id, date, time_slot)

    # 1. Acquire lock
    ok, token, ttl, msg = await acquire_slot_lock(
        doctor_id=doctor_id,
        date=date,
        time_slot=time_slot,
        user_id=user_id,
        ttl_seconds=30
    )
    assert ok is True
    assert token is not None
    assert ttl > 0

    # 2. Verify lock
    is_valid = await verify_slot_lock(doctor_id, date, time_slot, user_id, token)
    assert is_valid is True

    # 3. Another user should NOT be able to acquire same lock
    other_user = "user_xyz_789"
    ok2, token2, ttl2, msg2 = await acquire_slot_lock(
        doctor_id=doctor_id,
        date=date,
        time_slot=time_slot,
        user_id=other_user,
        ttl_seconds=30
    )
    assert ok2 is False
    assert token2 is None

    # 4. Check lock status
    is_locked, held_by_me, rem_ttl = await get_slot_lock_status(
        doctor_id, date, time_slot, current_user_id=user_id
    )
    assert is_locked is True
    assert held_by_me is True

    is_locked_other, held_by_other, _ = await get_slot_lock_status(
        doctor_id, date, time_slot, current_user_id=other_user
    )
    assert is_locked_other is True
    assert held_by_other is False

    # 5. Release lock
    released = await release_slot_lock(doctor_id, date, time_slot, user_id, token)
    assert released is True

    # 6. Verify lock is now released
    is_valid_after = await verify_slot_lock(doctor_id, date, time_slot, user_id, token)
    assert is_valid_after is False

    is_locked_now, _, _ = await get_slot_lock_status(doctor_id, date, time_slot)
    assert is_locked_now is False


@pytest.mark.asyncio
async def test_wrong_token_cannot_release():
    doctor_id = "doc_test_123"
    date = "2026-10-15"
    time_slot = "11:00 AM"
    user_id = "user_abc_456"

    await force_release_slot_lock(doctor_id, date, time_slot)

    ok, token, _, _ = await acquire_slot_lock(doctor_id, date, time_slot, user_id, 30)
    assert ok is True

    # Attempt release with fraudulent token
    failed_release = await release_slot_lock(doctor_id, date, time_slot, user_id, "fraudulent_token_999")
    assert failed_release is False

    # Clean up
    await release_slot_lock(doctor_id, date, time_slot, user_id, token)
