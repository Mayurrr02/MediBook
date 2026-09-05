import pytest
import datetime
from models import (
    DoctorAvailability,
    DoctorLeave,
    ConsultationType,
    AppointmentStatus,
)
from services.scheduling_service import (
    calculate_available_slots,
    save_doctor_availability,
)
from database import db


@pytest.mark.asyncio
async def test_non_working_day_returns_no_slots():
    doc_id = "60c72b2f9b1d8b2bad000001"
    # 2026-10-18 is a Sunday (weekday 6)
    sunday_date = "2026-10-18"

    response = await calculate_available_slots(
        doctor_id=doc_id,
        date_str=sunday_date,
    )

    assert response.total_available == 0
    assert len(response.available_slots) == 0
    assert len(response.unavailable_periods) > 0
    assert "does not consult" in response.unavailable_periods[0].reason


@pytest.mark.asyncio
async def test_doctor_leave_marks_day_unavailable():
    doc_id = "60c72b2f9b1d8b2bad000002"
    leave_date = "2026-10-14"  # Wednesday

    # Simulate doctor leave in DB
    await db.doctor_leaves.insert_one({
        "doctor_id": doc_id,
        "start_date": leave_date,
        "end_date": leave_date,
        "reason": "Annual Medical Conference",
    })

    response = await calculate_available_slots(
        doctor_id=doc_id,
        date_str=leave_date,
    )

    assert response.is_on_leave is True
    assert response.leave_reason == "Annual Medical Conference"
    assert response.total_available == 0
    assert len(response.available_slots) == 0
    assert len(response.unavailable_periods) > 0
    assert "Annual Medical Conference" in response.unavailable_periods[0].reason

    # Clean up
    await db.doctor_leaves.delete_many({"doctor_id": doc_id})


@pytest.mark.asyncio
async def test_past_date_slot_generation():
    doc_id = "60c72b2f9b1d8b2bad000001"
    past_date = "2020-01-01"

    response = await calculate_available_slots(
        doctor_id=doc_id,
        date_str=past_date,
    )

    # All slots in the past must be filtered out
    assert response.total_available == 0
    assert len(response.available_slots) == 0
