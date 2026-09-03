import datetime
import logging
from typing import List, Optional, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId

from database import db
from models import (
    DoctorScheduleConfig,
    WorkingShift,
    SlotInfo,
    SlotStatus,
    DoctorSlotsResponse,
    AppointmentStatus,
)
from services.lock_service import get_slot_lock_status

logger = logging.getLogger("medibook.scheduling")

DEFAULT_WORKING_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday
DEFAULT_SLOT_DURATION = 30  # minutes
DEFAULT_SHIFTS = [WorkingShift(start_time="09:00", end_time="17:00", break_start="13:00", break_end="14:00")]


def _parse_time_str(time_str: str) -> datetime.time:
    """Parses 'HH:MM' or 'HH:MM AM/PM' into a datetime.time object."""
    clean = time_str.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.datetime.strptime(clean, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"Invalid time format: {time_str}")


def _format_time_display(dt: datetime.time) -> str:
    """Formats datetime.time into standard display string 'HH:MM AM/PM'."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _is_time_in_break(time_slot: datetime.time, duration_min: int, break_start_str: Optional[str], break_end_str: Optional[str]) -> bool:
    if not break_start_str or not break_end_str:
        return False
    try:
        b_start = _parse_time_str(break_start_str)
        b_end = _parse_time_str(break_end_str)
        slot_end = (datetime.datetime.combine(datetime.date.today(), time_slot) + datetime.timedelta(minutes=duration_min)).time()
        return (time_slot < b_end) and (slot_end > b_start)
    except Exception:
        return False


def generate_time_slots_for_shift(shift: WorkingShift, slot_duration_minutes: int) -> List[str]:
    """Generates a list of time slot strings (e.g. '9:00 AM') for a given shift."""
    start_t = _parse_time_str(shift.start_time)
    end_t = _parse_time_str(shift.end_time)

    slots = []
    current_dt = datetime.datetime.combine(datetime.date.today(), start_t)
    end_dt = datetime.datetime.combine(datetime.date.today(), end_t)

    while current_dt + datetime.timedelta(minutes=slot_duration_minutes) <= end_dt:
        t = current_dt.time()
        if not _is_time_in_break(t, slot_duration_minutes, shift.break_start, shift.break_end):
            slots.append(_format_time_display(t))
        current_dt += datetime.timedelta(minutes=slot_duration_minutes)

    return slots


async def get_doctor_schedule_config(doctor_id: str) -> DoctorScheduleConfig:
    """Retrieves schedule config for a doctor from DB or returns standard defaults."""
    try:
        doc_schedule = await db.doctor_schedules.find_one({"doctor_id": str(doctor_id)})
        if doc_schedule:
            shifts = [WorkingShift(**s) for s in doc_schedule.get("shifts", [])] or DEFAULT_SHIFTS
            return DoctorScheduleConfig(
                doctor_id=str(doctor_id),
                slot_duration_minutes=doc_schedule.get("slot_duration_minutes", DEFAULT_SLOT_DURATION),
                working_days=doc_schedule.get("working_days", DEFAULT_WORKING_DAYS),
                shifts=shifts,
                blocked_dates=doc_schedule.get("blocked_dates", []),
            )
    except Exception as e:
        logger.warning(f"Could not read doctor schedule from DB: {e}")

    # Fallback to default schedule
    return DoctorScheduleConfig(
        doctor_id=str(doctor_id),
        slot_duration_minutes=DEFAULT_SLOT_DURATION,
        working_days=DEFAULT_WORKING_DAYS,
        shifts=DEFAULT_SHIFTS,
        blocked_dates=[],
    )


async def save_doctor_schedule_config(doctor_id: str, config: DoctorScheduleConfig) -> DoctorScheduleConfig:
    """Saves or updates doctor's schedule configuration."""
    data = {
        "doctor_id": str(doctor_id),
        "slot_duration_minutes": config.slot_duration_minutes,
        "working_days": config.working_days,
        "shifts": [s.dict() for s in config.shifts],
        "blocked_dates": config.blocked_dates,
        "updated_at": datetime.datetime.utcnow(),
    }
    await db.doctor_schedules.update_one(
        {"doctor_id": str(doctor_id)},
        {"$set": data},
        upsert=True
    )
    return config


async def compute_doctor_slots(
    doctor_id: str,
    date_str: str,
    current_user_id: Optional[str] = None
) -> DoctorSlotsResponse:
    """
    Computes dynamic slots and their real-time availability status
    (AVAILABLE, LOCKED, BOOKED, BLOCKED) for a given doctor on a specific date.
    """
    # 1. Fetch doctor details
    doctor = None
    try:
        doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except Exception:
        doctor = None

    doc_name = doctor["name"] if (doctor and "name" in doctor) else "Doctor"
    specialization = doctor.get("specialization", "General Medicine") if doctor else "General Medicine"

    # 2. Parse date & check working days / blocked dates
    try:
        req_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format. Expected YYYY-MM-DD")

    schedule_cfg = await get_doctor_schedule_config(doctor_id)

    # Check if blocked date or non-working day
    is_blocked_date = date_str in schedule_cfg.blocked_dates
    is_working_day = req_date.weekday() in schedule_cfg.working_days

    # Generate all candidate slot strings
    candidate_slot_strings = []
    if is_working_day and not is_blocked_date:
        for shift in schedule_cfg.shifts:
            candidate_slot_strings.extend(
                generate_time_slots_for_shift(shift, schedule_cfg.slot_duration_minutes)
            )

    # If no shifts configured or default fallback needed
    if not candidate_slot_strings and is_working_day and not is_blocked_date:
        candidate_slot_strings = [
            "9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM",
            "2:00 PM", "2:30 PM", "3:00 PM", "3:30 PM", "4:00 PM", "4:30 PM"
        ]

    # 3. Query active bookings for this doctor & date
    active_statuses = [
        AppointmentStatus.CONFIRMED.value,
        AppointmentStatus.PENDING_CONFIRMATION.value,
        AppointmentStatus.IN_PROGRESS.value,
        "confirmed", "pending", "booked"
    ]

    booked_times = set()
    try:
        booked_appointments_cursor = db.appointments.find({
            "doctor_id": str(doctor_id),
            "date": date_str,
            "status": {"$in": active_statuses}
        })
        async for appt in booked_appointments_cursor:
            time_val = appt.get("time", "")
            try:
                parsed_t = _parse_time_str(time_val)
                booked_times.add(_format_time_display(parsed_t))
            except Exception:
                booked_times.add(time_val.strip())
    except Exception as e:
        logger.warning(f"Could not query appointments from DB: {e}")

    # 4. Check lock status and construct SlotInfo list
    slot_info_list: List[SlotInfo] = []
    available_count = 0

    today = datetime.date.today()
    now_time = datetime.datetime.now().time()
    is_past_day = req_date < today

    for slot_time in candidate_slot_strings:
        # Check if slot in past for today
        is_past_slot = False
        if req_date == today:
            try:
                if _parse_time_str(slot_time) <= now_time:
                    is_past_slot = True
            except Exception:
                pass

        if is_past_day or is_past_slot or is_blocked_date:
            slot_info_list.append(SlotInfo(
                doctor_id=str(doctor_id),
                date=date_str,
                time=slot_time,
                status=SlotStatus.BLOCKED,
            ))
            continue

        if slot_time in booked_times:
            slot_info_list.append(SlotInfo(
                doctor_id=str(doctor_id),
                date=date_str,
                time=slot_time,
                status=SlotStatus.BOOKED,
            ))
            continue

        # Check Redis/in-memory distributed lock status
        is_locked, held_by_me, remaining_ttl = await get_slot_lock_status(
            doctor_id=str(doctor_id),
            date=date_str,
            time_slot=slot_time,
            current_user_id=current_user_id
        )

        if is_locked:
            slot_info_list.append(SlotInfo(
                doctor_id=str(doctor_id),
                date=date_str,
                time=slot_time,
                status=SlotStatus.LOCKED,
                held_by_current_user=held_by_me,
                expires_in_seconds=remaining_ttl,
            ))
            if held_by_me:
                available_count += 1
        else:
            slot_info_list.append(SlotInfo(
                doctor_id=str(doctor_id),
                date=date_str,
                time=slot_time,
                status=SlotStatus.AVAILABLE,
            ))
            available_count += 1

    return DoctorSlotsResponse(
        doctor_id=str(doctor_id),
        doctor_name=doc_name,
        specialization=specialization,
        date=date_str,
        slot_duration_minutes=schedule_cfg.slot_duration_minutes,
        total_slots=len(slot_info_list),
        available_slots=available_count,
        slots=slot_info_list
    )
