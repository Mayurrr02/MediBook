import pytest
from bson import ObjectId
from fastapi import HTTPException
from database import db
from models import ConsultationType, AppointmentStatus
from services.appointment_service import book_appointment


@pytest.mark.asyncio
async def test_booking_validation_and_success():
    # Insert mock doctor
    doc_res = await db.doctors.insert_one({
        "name": "Dr. Sarah Jenkins",
        "specialization": "Cardiology",
        "experience": 12,
        "fee": 500,
    })
    doctor_id = str(doc_res.inserted_id)

    user = {
        "_id": "60c72b2f9b1d8b2bad000099",
        "name": "John Doe",
        "email": "john@example.com",
    }

    booking_date = "2026-11-16"  # Monday
    booking_time = "10:00"

    # 1. Successful Booking
    result = await book_appointment(
        doctor_id=doctor_id,
        date=booking_date,
        time_slot=booking_time,
        user=user,
        consultation_type=ConsultationType.IN_PERSON,
        reason="Heart checkup",
    )

    assert result["status"] == AppointmentStatus.CONFIRMED.value
    assert result["doctor_id"] == doctor_id
    assert result["date"] == booking_date
    assert result["time"] == "10:00"
    assert result["end_time"] == "10:30"
    appointment_id = result["id"]

    # 2. Attempting to book the SAME slot should raise 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        await book_appointment(
            doctor_id=doctor_id,
            date=booking_date,
            time_slot=booking_time,
            user=user,
        )
    assert exc_info.value.status_code == 409
    assert "already booked" in exc_info.value.detail.lower()

    # 3. Booking on past date should raise 400 Bad Request
    with pytest.raises(HTTPException) as exc_past:
        await book_appointment(
            doctor_id=doctor_id,
            date="2020-01-01",
            time_slot="10:00",
            user=user,
        )
    assert exc_past.value.status_code == 400
    assert "past" in exc_past.value.detail.lower()

    # 4. Booking non-existent doctor should raise 404 Not Found
    with pytest.raises(HTTPException) as exc_not_found:
        await book_appointment(
            doctor_id="60c72b2f9b1d8b2bad000000",
            date=booking_date,
            time_slot="14:00",
            user=user,
        )
    assert exc_not_found.value.status_code == 404

    # Cleanup
    await db.doctors.delete_one({"_id": ObjectId(doctor_id)})
    await db.appointments.delete_many({"doctor_id": doctor_id})
