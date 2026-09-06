import pytest
import asyncio
from bson import ObjectId
from fastapi import HTTPException
from database import db
from models import ConsultationType
from services.appointment_service import book_appointment
from services.lock_service import force_release_slot_lock


@pytest.mark.asyncio
async def test_100_concurrent_bookings_on_same_slot():
    """
    Simulates 100 concurrent users firing booking requests for the EXACT same doctor, date, and slot simultaneously.
    Verifies that the distributed lock + database state check ensures strictly 1 booking succeeds
    and all 99 other requests receive 409 Conflict without race conditions or double bookings.
    """
    # Create test doctor
    doc_res = await db.doctors.insert_one({
        "name": "Dr. High Concurrency",
        "specialization": "Emergency Medicine",
        "experience": 20,
        "fee": 1000,
    })
    doctor_id = str(doc_res.inserted_id)
    test_date = "2026-12-07"  # Monday
    test_time = "10:00"

    await force_release_slot_lock(doctor_id, test_date, test_time)

    async def attempt_booking(user_num: int):
        user_id = f"60c72b2f9b1d8b2bad000{user_num:03d}"
        user_dict = {
            "_id": user_id,
            "id": user_id,
            "name": f"Patient {user_num}",
            "email": f"patient{user_num}@test.com",
        }
        try:
            res = await book_appointment(
                doctor_id=doctor_id,
                date=test_date,
                time_slot=test_time,
                user=user_dict,
                consultation_type=ConsultationType.IN_PERSON,
                reason="Routine check",
            )
            return {"user": user_num, "status": "SUCCESS", "res": res}
        except HTTPException as exc:
            return {"user": user_num, "status": "REJECTED", "code": exc.status_code, "detail": exc.detail}
        except Exception as e:
            return {"user": user_num, "status": "ERROR", "error": str(e)}

    # Fire 100 concurrent requests simultaneously using asyncio.gather
    tasks = [attempt_booking(i) for i in range(1, 101)]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r["status"] == "SUCCESS"]
    rejected = [r for r in results if r["status"] == "REJECTED"]
    errors = [r for r in results if r["status"] == "ERROR"]

    assert len(errors) == 0, f"Encountered unexpected errors: {errors}"
    assert len(successes) == 1, f"Expected exactly 1 successful booking, but got {len(successes)}"
    assert len(rejected) == 99, f"Expected 99 rejected bookings, but got {len(rejected)}"

    for r in rejected:
        assert r["code"] == 409, f"Expected 409 Conflict, got {r['code']}"

    # Verify database has strictly 1 appointment document for this slot
    db_count = 0
    async for _ in db.appointments.find({"doctor_id": doctor_id, "date": test_date, "time": test_time, "status": "CONFIRMED"}):
        db_count += 1

    assert db_count == 1, f"Database has {db_count} appointments booked for the same slot!"

    # Clean up
    await db.doctors.delete_one({"_id": ObjectId(doctor_id)})
    await db.appointments.delete_many({"doctor_id": doctor_id})
    await force_release_slot_lock(doctor_id, test_date, test_time)
