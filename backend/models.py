from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class AppointmentStatus(str, Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    NO_SHOW = "NO_SHOW"


class SlotStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    LOCKED = "LOCKED"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"


# --- Auth Models ---
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: Optional[UserRole] = UserRole.PATIENT


class Login(BaseModel):
    email: EmailStr
    password: str


# --- Doctor & Schedule Models ---
class WorkingShift(BaseModel):
    start_time: str = "09:00"  # 24hr HH:MM format
    end_time: str = "17:00"
    break_start: Optional[str] = "13:00"
    break_end: Optional[str] = "14:00"


class DoctorScheduleConfig(BaseModel):
    doctor_id: Optional[str] = None
    slot_duration_minutes: int = Field(default=30, ge=10, le=120)
    working_days: List[int] = Field(default=[0, 1, 2, 3, 4])  # 0=Monday, 6=Sunday
    shifts: List[WorkingShift] = Field(default_factory=lambda: [WorkingShift()])
    blocked_dates: List[str] = Field(default_factory=list)  # ["YYYY-MM-DD"]


class Doctor(BaseModel):
    name: str
    specialization: str
    experience: int
    fee: int
    bio: Optional[str] = None
    user_id: Optional[str] = None  # Link to a user account if doctor logs in
    schedule: Optional[DoctorScheduleConfig] = None


# --- Slot Locking & Availability Models ---
class SlotInfo(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "09:00 AM" or "09:00"
    status: SlotStatus
    held_by_current_user: bool = False
    expires_in_seconds: Optional[int] = None


class DoctorSlotsResponse(BaseModel):
    doctor_id: str
    doctor_name: Optional[str] = None
    specialization: Optional[str] = None
    date: str
    slot_duration_minutes: int
    total_slots: int
    available_slots: int
    slots: List[SlotInfo]


class LockSlotRequest(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "10:00 AM"
    ttl_seconds: Optional[int] = 300


class LockSlotResponse(BaseModel):
    success: bool
    lock_token: Optional[str] = None
    doctor_id: str
    date: str
    time: str
    expires_in_seconds: Optional[int] = None
    message: str


class UnlockSlotRequest(BaseModel):
    doctor_id: str
    date: str
    time: str
    lock_token: str


# --- Appointment Lifecycle Models ---
class Appointment(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "10:00 AM"
    lock_token: Optional[str] = None
    reason: Optional[str] = None
    patient_notes: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = "Patient requested cancellation"


class RescheduleAppointmentRequest(BaseModel):
    new_date: str
    new_time: str
    new_lock_token: Optional[str] = None
    reason: Optional[str] = None


class UpdateAppointmentStatusRequest(BaseModel):
    status: AppointmentStatus
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str
    specialization: str
    user_id: str
    user_name: Optional[str] = None
    date: str
    time: str
    status: AppointmentStatus
    reason: Optional[str] = None
    patient_notes: Optional[str] = None
    created_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None


# --- Payment Models ---
class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str = "INR"
    key: str


class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# --- AI Models ---
class SymptomCheckRequest(BaseModel):
    symptoms: str = Field(min_length=3, max_length=1000)
