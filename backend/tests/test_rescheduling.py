import pytest
from bson import ObjectId
from fastapi import HTTPException
from database import db
from models import AppointmentStatus
from services.appointment_service import (
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
)


@pytest.mark.asyncio
async def test_appointment_rescheduling():
    doc_res = await db.doctors.insert_one({
        "name": "Dr. Clara Oswald",
        "specialization": "Neurology",
        "experience": 15,
        "fee": 600,
    })
    doctor_id = str(doc_res.inserted_id)

    user = {"_id": "60c72b2f9b1d8b2bad000003", "name": "Charlie", "email": "charlie@example.com"}

    orig_date = "2026-11-24"
    orig_time = "09:00"

    # Book original appointment
    orig_appt = await book_appointment(
        doctor_id=doctor_id,
        date=orig_date,
        time_slot=orig_time,
        user=user,
    )
    orig_id = orig_appt["id"]

    new_date = "2026-11-25"
    new_time = "14:00"

    # 1. Reschedule appointment
    resched_result = await reschedule_appointment(
        appointment_id=orig_id,
        new_date=new_date,
        new_time=new_time,
        user=user,
        reason="Need afternoon slot instead",
    )

    assert "rescheduled successfully" in resched_result["message"].lower()
    new_id = resched_result["new_appointment"]["id"]

    # 2. Check old appointment is marked CANCELLED with link to new
    old_doc = await db.appointments.find_one({"_id": ObjectId(orig_id)})
    assert old_doc["status"] == AppointmentStatus.CANCELLED.value
    assert old_doc["rescheduled_to"] == new_id

    # 3. Check new appointment is CONFIRMED with link from old
    new_doc = await db.appointments.find_one({"_id": ObjectId(new_id)})
    assert new_doc["status"] == AppointmentStatus.CONFIRMED.value
    assert new_doc["date"] == new_date
    assert new_doc["time"] == "14:00"
    assert new_doc["rescheduled_from"] == orig_id

    # 4. Attempting to reschedule an already cancelled appointment should fail
    with pytest.raises(HTTPException) as exc_cancelled:
        await reschedule_appointment(
            appointment_id=orig_id,
            new_date="2026-11-26",
            new_time="10:00",
            user=user,
        )
    assert exc_cancelled.value.status_code == 400

    # Clean up
    await db.doctors.delete_one({"_id": ObjectId(doctor_id)})
    await db.appointments.delete_many({"doctor_id": doctor_id})
