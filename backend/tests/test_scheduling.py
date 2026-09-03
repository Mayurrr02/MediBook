import pytest
import datetime
from services.scheduling_service import (
    generate_time_slots_for_shift,
    _parse_time_str,
    _format_time_display,
    _is_time_in_break,
)
from models import WorkingShift


def test_time_parsing_and_formatting():
    t1 = _parse_time_str("09:00")
    assert t1.hour == 9 and t1.minute == 0
    assert _format_time_display(t1) == "9:00 AM"

    t2 = _parse_time_str("14:30")
    assert t2.hour == 14 and t2.minute == 30
    assert _format_time_display(t2) == "2:30 PM"

    t3 = _parse_time_str("10:00 AM")
    assert t3.hour == 10 and t3.minute == 0


def test_break_overlap_detection():
    # Break from 13:00 to 14:00 (1:00 PM to 2:00 PM)
    break_start = "13:00"
    break_end = "14:00"

    # Slot at 12:30 for 30 min (ends 13:00) -> Not in break
    slot_1230 = _parse_time_str("12:30")
    assert not _is_time_in_break(slot_1230, 30, break_start, break_end)

    # Slot at 13:00 for 30 min (ends 13:30) -> In break
    slot_1300 = _parse_time_str("13:00")
    assert _is_time_in_break(slot_1300, 30, break_start, break_end)

    # Slot at 13:30 for 30 min (ends 14:00) -> In break
    slot_1330 = _parse_time_str("13:30")
    assert _is_time_in_break(slot_1330, 30, break_start, break_end)

    # Slot at 14:00 for 30 min (ends 14:30) -> Not in break
    slot_1400 = _parse_time_str("14:00")
    assert not _is_time_in_break(slot_1400, 30, break_start, break_end)


def test_slot_generation_for_shift():
    shift = WorkingShift(
        start_time="09:00",
        end_time="12:00",
        break_start=None,
        break_end=None,
    )
    # 30 min slots from 9:00 to 12:00
    slots = generate_time_slots_for_shift(shift, slot_duration_minutes=30)
    assert slots == ["9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM"]
    assert len(slots) == 6


def test_slot_generation_with_break():
    shift = WorkingShift(
        start_time="09:00",
        end_time="13:00",
        break_start="10:00",
        break_end="11:00",
    )
    # 30 min slots: 9:00, 9:30, (skip 10:00, 10:30), 11:00, 11:30, 12:00, 12:30
    slots = generate_time_slots_for_shift(shift, slot_duration_minutes=30)
    assert "9:00 AM" in slots
    assert "9:30 AM" in slots
    assert "10:00 AM" not in slots
    assert "10:30 AM" not in slots
    assert "11:00 AM" in slots
    assert "12:30 PM" in slots
    assert len(slots) == 6
