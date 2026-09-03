import pytest
import asyncio
from services.lock_service import acquire_slot_lock, force_release_slot_lock


@pytest.mark.asyncio
async def test_concurrent_slot_lock_race_condition():
    """
    Simulates 20 concurrent users attempting to lock the exact same doctor time slot simultaneously.
    Proves that exactly 1 user succeeds and the other 19 receive False without race condition double-locks.
    """
    doctor_id = "doc_race_test_999"
    date = "2026-11-20"
    time_slot = "2:00 PM"

    await force_release_slot_lock(doctor_id, date, time_slot)

    async def attempt_lock(user_index: int):
        user_id = f"user_{user_index}"
        ok, token, ttl, msg = await acquire_slot_lock(
            doctor_id=doctor_id,
            date=date,
            time_slot=time_slot,
            user_id=user_id,
            ttl_seconds=30
        )
        return {"user_id": user_id, "success": ok, "token": token}

    # Launch 20 concurrent tasks
    tasks = [attempt_lock(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    assert len(successes) == 1, f"Expected exactly 1 successful lock, got {len(successes)}"
    assert len(failures) == 19, f"Expected 19 failed lock attempts, got {len(failures)}"

    # Clean up
    winner = successes[0]
    await force_release_slot_lock(doctor_id, date, time_slot)
