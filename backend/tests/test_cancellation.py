import pytest
from bson import ObjectId
from fastapi import HTTPException
from database import db
from models import AppointmentStatus
from services.appointment_service import book_appointment, cancel_appointment


@pytest.mark.asyncio
async def test_appointment_cancellation():
    doc_res = await db.doctors.insert_one({
        "name": "Dr. Alan Grant",
        "specialization": "Pediatrics",
        "experience": 8,
        "fee": 400,
    })
    doctor_id = str(doc_res.inserted_id)

    user1 = {"_id": "60c72b2f9b1d8b2bad000001", "name": "Alice", "email": "alice@example.com"}
    user2 = {"_id": "60c72b2f9b1d8b2bad000002", "name": "Bob", "email": "bob@example.com"}

    booking_date = "2026-11-23"
    booking_time = "11:00"

    appt = await book_appointment(
        doctor_id=doctor_id,
        date=booking_date,
        time_slot=booking_time,
        user=user1,
    )
    appointment_id = appt["id"]

    # 1. Unauthorized user attempting to cancel should raise 403 Forbidden
    with pytest.raises(HTTPException) as exc_auth:
        await cancel_appointment(
            appointment_id=appointment_id,
            user=user2,
            reason="I want to cancel Bob's appointment"
        )
    assert exc_auth.value.status_code == 403

    # 2. Owner cancels appointment
    cancel_res = await cancel_appointment(
        appointment_id=appointment_id,
        user=user1,
        reason="Schedule conflict with work"
    )
    assert cancel_res["status"] == AppointmentStatus.CANCELLED.value
    assert cancel_res["cancellation_reason"] == "Schedule conflict with work"

    # 3. Verify record was NOT physically deleted in MongoDB
    saved_doc = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    assert saved_doc is not None
    assert saved_doc["status"] == AppointmentStatus.CANCELLED.value
    assert saved_doc["cancelled_by"] == "60c72b2f9b1d8b2bad000001"
    assert "cancelled_at" in saved_doc
    assert saved_doc["cancellation_reason"] == "Schedule conflict with work"

    # Clean up
    await db.doctors.delete_one({"_id": ObjectId(doctor_id)})
    await db.appointments.delete_many({"doctor_id": doctor_id})
