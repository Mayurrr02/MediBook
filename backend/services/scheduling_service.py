import datetime
import logging
from typing import List, Optional, Tuple, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId

from database import db
from models import (
    DoctorAvailability,
    DoctorLeave,
    WorkingShift,
    BreakPeriod,
    SlotItem,
    UnavailablePeriod,
    AvailableSlotsResponse,
    AppointmentStatus,
    ConsultationType,
)

logger = logging.getLogger("medibook.scheduling")

DEFAULT_WORKING_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday
DEFAULT_DURATION = 30  # minutes
DEFAULT_BUFFER = 10  # minutes
DEFAULT_SHIFTS = [
    WorkingShift(start_time="09:00", end_time="13:00"),
    WorkingShift(start_time="14:00", end_time="18:00"),
]
DEFAULT_BREAKS = [
    BreakPeriod(start_time="13:00", end_time="14:00", title="Lunch Break")
]


def parse_time(time_str: str) -> datetime.time:
    """Parses 'HH:MM' or 'HH:MM AM/PM' into datetime.time."""
    clean = time_str.strip().upper()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.datetime.strptime(clean, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"Invalid time format: {time_str}")


def format_time_24(t: datetime.time) -> str:
    """Formats datetime.time to 'HH:MM' (24-hour)."""
    return t.strftime("%H:%M")


def format_time_12(t: datetime.time) -> str:
    """Formats datetime.time to 'H:MM AM/PM'."""
    return t.strftime("%I:%M %p").lstrip("0")


def add_minutes(t: datetime.time, minutes: int) -> datetime.time:
    """Adds minutes to a time object (clamped within same day)."""
    dummy_dt = datetime.datetime.combine(datetime.date.today(), t)
    new_dt = dummy_dt + datetime.timedelta(minutes=minutes)
    return new_dt.time()


def minutes_difference(t1: datetime.time, t2: datetime.time) -> int:
    """Calculates minutes between t1 and t2 (t2 - t1)."""
    d1 = datetime.datetime.combine(datetime.date.today(), t1)
    d2 = datetime.datetime.combine(datetime.date.today(), t2)
    return int((d2 - d1).total_seconds() // 60)


def is_overlapping(start_a: datetime.time, end_a: datetime.time, start_b: datetime.time, end_b: datetime.time) -> bool:
    """Checks if interval [start_a, end_a) overlaps with [start_b, end_b)."""
    return (start_a < end_b) and (end_a > start_b)


async def get_doctor_availability(doctor_id: str) -> DoctorAvailability:
    """Fetches doctor availability configuration or returns standard defaults."""
    try:
        doc_avail = await db.doctor_availabilities.find_one({"doctor_id": str(doctor_id)})
        if doc_avail:
            shifts = [WorkingShift(**s) for s in doc_avail.get("shifts", [])] or DEFAULT_SHIFTS
            breaks = [BreakPeriod(**b) for b in doc_avail.get("breaks", [])] or DEFAULT_BREAKS
            return DoctorAvailability(
                doctor_id=str(doctor_id),
                working_days=doc_avail.get("working_days", DEFAULT_WORKING_DAYS),
                shifts=shifts,
                breaks=breaks,
                duration_minutes=doc_avail.get("duration_minutes", DEFAULT_DURATION),
                buffer_minutes=doc_avail.get("buffer_minutes", DEFAULT_BUFFER),
                emergency_slots=doc_avail.get("emergency_slots", []),
                consultation_types=doc_avail.get(
                    "consultation_types",
                    [ConsultationType.IN_PERSON, ConsultationType.VIDEO]
                ),
            )
    except Exception as e:
        logger.warning(f"Error loading doctor availability from DB: {e}")

    return DoctorAvailability(
        doctor_id=str(doctor_id),
        working_days=DEFAULT_WORKING_DAYS,
        shifts=DEFAULT_SHIFTS,
        breaks=DEFAULT_BREAKS,
        duration_minutes=DEFAULT_DURATION,
        buffer_minutes=DEFAULT_BUFFER,
        emergency_slots=[],
        consultation_types=[ConsultationType.IN_PERSON, ConsultationType.VIDEO],
    )


async def save_doctor_availability(doctor_id: str, avail: DoctorAvailability) -> DoctorAvailability:
    """Upserts doctor availability configuration."""
    data = {
        "doctor_id": str(doctor_id),
        "working_days": avail.working_days,
        "shifts": [s.dict() for s in avail.shifts],
        "breaks": [b.dict() for b in avail.breaks],
        "duration_minutes": avail.duration_minutes,
        "buffer_minutes": avail.buffer_minutes,
        "emergency_slots": avail.emergency_slots,
        "consultation_types": [ct.value for ct in avail.consultation_types],
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }
    await db.doctor_availabilities.update_one(
        {"doctor_id": str(doctor_id)},
        {"$set": data},
        upsert=True
    )
    return avail


async def check_doctor_leave(doctor_id: str, date_str: str) -> Optional[DoctorLeave]:
    """Checks if doctor is on approved leave for the specified date."""
    try:
        leave_doc = await db.doctor_leaves.find_one({
            "doctor_id": str(doctor_id),
            "start_date": {"$lte": date_str},
            "end_date": {"$gte": date_str},
        })
        if leave_doc:
            return DoctorLeave(
                id=str(leave_doc.get("_id", "")),
                doctor_id=str(doctor_id),
                start_date=leave_doc.get("start_date"),
                end_date=leave_doc.get("end_date"),
                reason=leave_doc.get("reason", "On Leave"),
            )
    except Exception as e:
        logger.warning(f"Error checking doctor leave: {e}")
    return None


async def calculate_available_slots(
    doctor_id: str,
    date_str: str,
    appointment_type: Optional[ConsultationType] = None
) -> AvailableSlotsResponse:
    """
    Dynamically calculates available slots, booked slots, and unavailable periods
    for a doctor on a specific date considering shifts, breaks, buffer time, leaves,
    current time, and existing bookings.
    """
    # 1. Fetch Doctor details
    doctor = None
    try:
        doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except Exception:
        pass

    doc_name = doctor["name"] if (doctor and "name" in doctor) else "Doctor"
    specialization = doctor.get("specialization", "General Medicine") if doctor else "General Medicine"

    # 2. Parse Date
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format. Please use YYYY-MM-DD.")

    availability = await get_doctor_availability(doctor_id)

    # 3. Check Leave
    leave = await check_doctor_leave(doctor_id, date_str)
    if leave:
        return AvailableSlotsResponse(
            doctor_id=str(doctor_id),
            doctor_name=doc_name,
            specialization=specialization,
            date=date_str,
            duration_minutes=availability.duration_minutes,
            buffer_minutes=availability.buffer_minutes,
            consultation_type=appointment_type.value if appointment_type else None,
            is_on_leave=True,
            leave_reason=leave.reason,
            total_available=0,
            total_booked=0,
            available_slots=[],
            booked_slots=[],
            unavailable_periods=[
                UnavailablePeriod(
                    start_time="00:00",
                    end_time="23:59",
                    reason=f"Doctor on Leave: {leave.reason}"
                )
            ]
        )

    # 4. Check Working Day
    day_of_week = target_date.weekday()  # 0=Mon, 6=Sun
    if day_of_week not in availability.working_days:
        return AvailableSlotsResponse(
            doctor_id=str(doctor_id),
            doctor_name=doc_name,
            specialization=specialization,
            date=date_str,
            duration_minutes=availability.duration_minutes,
            buffer_minutes=availability.buffer_minutes,
            consultation_type=appointment_type.value if appointment_type else None,
            is_on_leave=False,
            total_available=0,
            total_booked=0,
            available_slots=[],
            booked_slots=[],
            unavailable_periods=[
                UnavailablePeriod(
                    start_time="00:00",
                    end_time="23:59",
                    reason="Doctor does not consult on this day of the week"
                )
            ]
        )

    # 5. Query Existing Active Bookings
    active_statuses = [
        AppointmentStatus.CONFIRMED.value,
        AppointmentStatus.HELD.value,
        "confirmed",
        "pending",
    ]
    booked_slots_data: List[SlotItem] = []
    booked_time_intervals: List[Tuple[datetime.time, datetime.time]] = []

    try:
        cursor = db.appointments.find({
            "doctor_id": str(doctor_id),
            "date": date_str,
            "status": {"$in": active_statuses}
        })
        async for appt in cursor:
            t_str = appt.get("time", "")
            try:
                b_start = parse_time(t_str)
                dur = appt.get("duration_minutes", availability.duration_minutes)
                b_end = add_minutes(b_start, dur)
                booked_time_intervals.append((b_start, b_end))

                c_type = appt.get("consultation_type", ConsultationType.IN_PERSON.value)
                try:
                    c_enum = ConsultationType(c_type)
                except Exception:
                    c_enum = ConsultationType.IN_PERSON

                booked_slots_data.append(SlotItem(
                    time=format_time_24(b_start),
                    end_time=format_time_24(b_end),
                    status=AppointmentStatus.CONFIRMED,
                    is_emergency=False,
                    consultation_type=c_enum,
                ))
            except Exception as e:
                logger.warning(f"Could not parse booked appointment time {t_str}: {e}")
    except Exception as e:
        logger.warning(f"Error querying booked appointments: {e}")

    # 6. Parse Shifts & Breaks
    unavailable_periods_data: List[UnavailablePeriod] = []
    for b in availability.breaks:
        unavailable_periods_data.append(UnavailablePeriod(
            start_time=b.start_time,
            end_time=b.end_time,
            reason=b.title or "Scheduled Break"
        ))

    # 7. Generate Candidate Slots
    duration = availability.duration_minutes
    buffer_min = availability.buffer_minutes
    emergency_slot_set = set(availability.emergency_slots)

    now = datetime.datetime.now()
    today_date = now.date()
    current_time = now.time()
    is_today = (target_date == today_date)
    is_past_day = (target_date < today_date)

    available_slots_data: List[SlotItem] = []

    for shift in availability.shifts:
        try:
            shift_start = parse_time(shift.start_time)
            shift_end = parse_time(shift.end_time)
        except Exception:
            continue

        curr_start = shift_start

        while True:
            curr_end = add_minutes(curr_start, duration)

            # If slot exceeds shift end time, break shift loop
            if curr_end > shift_end or (curr_end < curr_start and shift_end < shift_start):
                break

            # Check break overlap
            in_break = False
            for b in availability.breaks:
                try:
                    b_start = parse_time(b.start_time)
                    b_end = parse_time(b.end_time)
                    if is_overlapping(curr_start, curr_end, b_start, b_end):
                        in_break = True
                        curr_start = b_end
                        break
                except Exception:
                    pass

            if in_break:
                continue

            curr_start_str = format_time_24(curr_start)
            curr_end_str = format_time_24(curr_end)

            # Check if booked
            is_booked = False
            for b_start, b_end in booked_time_intervals:
                if is_overlapping(curr_start, curr_end, b_start, b_end):
                    is_booked = True
                    break

            # Check if in past
            is_past_slot = is_past_day or (is_today and curr_start <= current_time)

            is_emergency = (curr_start_str in emergency_slot_set)

            if not is_booked and not is_past_slot:
                c_type = appointment_type or ConsultationType.IN_PERSON
                available_slots_data.append(SlotItem(
                    time=curr_start_str,
                    end_time=curr_end_str,
                    status=AppointmentStatus.AVAILABLE,
                    is_emergency=is_emergency,
                    consultation_type=c_type,
                ))

            # Advance by duration + buffer_minutes
            next_start = add_minutes(curr_end, buffer_min)
            if next_start <= curr_start:  # overflow protection
                break
            curr_start = next_start

    # Sort available slots by time
    available_slots_data.sort(key=lambda s: s.time)
    booked_slots_data.sort(key=lambda s: s.time)

    return AvailableSlotsResponse(
        doctor_id=str(doctor_id),
        doctor_name=doc_name,
        specialization=specialization,
        date=date_str,
        duration_minutes=duration,
        buffer_minutes=buffer_min,
        consultation_type=appointment_type.value if appointment_type else None,
        is_on_leave=False,
        total_available=len(available_slots_data),
        total_booked=len(booked_slots_data),
        available_slots=available_slots_data,
        booked_slots=booked_slots_data,
        unavailable_periods=unavailable_periods_data,
    )
