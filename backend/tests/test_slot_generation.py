import pytest
import datetime
from models import (
    DoctorAvailability,
    WorkingShift,
    BreakPeriod,
    ConsultationType,
    AppointmentStatus,
)
from services.scheduling_service import (
    calculate_available_slots,
    parse_time,
    format_time_24,
    add_minutes,
    is_overlapping,
)


def test_time_and_buffer_math():
    start = parse_time("09:00")
    duration = 30
    buffer_min = 10

    end = add_minutes(start, duration)
    assert format_time_24(end) == "09:30"

    next_slot = add_minutes(end, buffer_min)
    assert format_time_24(next_slot) == "09:40"


def test_shift_and_break_overlap():
    break_start = parse_time("13:00")
    break_end = parse_time("14:00")

    # Slot 12:40 - 13:10 overlaps with 13:00 - 14:00
    slot_start = parse_time("12:40")
    slot_end = parse_time("13:10")
    assert is_overlapping(slot_start, slot_end, break_start, break_end) is True

    # Slot 12:20 - 12:50 does NOT overlap
    slot_start2 = parse_time("12:20")
    slot_end2 = parse_time("12:50")
    assert is_overlapping(slot_start2, slot_end2, break_start, break_end) is False


@pytest.mark.asyncio
async def test_dynamic_slot_generation_with_buffer_and_shifts():
    # Pick a future Monday: 2026-10-12 is a Monday (weekday 0)
    future_date = "2026-10-12"
    doc_id = "60c72b2f9b1d8b2bad000001"

    response = await calculate_available_slots(
        doctor_id=doc_id,
        date_str=future_date,
        appointment_type=ConsultationType.IN_PERSON,
    )

    assert response.doctor_id == doc_id
    assert response.date == future_date
    assert response.duration_minutes == 30
    assert response.buffer_minutes == 10
    assert response.is_on_leave is False
    assert len(response.available_slots) > 0

    # First slot should be 09:00 - 09:30
    first_slot = response.available_slots[0]
    assert first_slot.time == "09:00"
    assert first_slot.end_time == "09:30"
    assert first_slot.status == AppointmentStatus.AVAILABLE

    # Second slot should be 09:40 - 10:10 (with 10 min buffer)
    second_slot = response.available_slots[1]
    assert second_slot.time == "09:40"
    assert second_slot.end_time == "10:10"

    # Ensure no slot starts inside the break period 13:00 - 14:00
    for slot in response.available_slots:
        st = parse_time(slot.time)
        assert not (parse_time("13:00") <= st < parse_time("14:00")), f"Slot {slot.time} generated inside break period"
