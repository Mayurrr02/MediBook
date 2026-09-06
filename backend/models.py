from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class AppointmentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"


class WaitlistStatus(str, Enum):
    WAITING = "WAITING"
    NOTIFIED = "NOTIFIED"
    BOOKED = "BOOKED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ConsultationType(str, Enum):
    IN_PERSON = "IN_PERSON"
    VIDEO = "VIDEO"


# --- Auth Models ---
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: Optional[UserRole] = UserRole.PATIENT


class Login(BaseModel):
    email: EmailStr
    password: str


# --- Doctor Availability & Leave Models ---
class WorkingShift(BaseModel):
    start_time: str = "09:00"  # 24hr HH:MM format
    end_time: str = "17:00"


class BreakPeriod(BaseModel):
    start_time: str = "13:00"
    end_time: str = "14:00"
    title: str = "Lunch Break"


class DoctorAvailability(BaseModel):
    doctor_id: Optional[str] = None
    working_days: List[int] = Field(default=[0, 1, 2, 3, 4])  # 0=Monday, 4=Friday
    shifts: List[WorkingShift] = Field(
        default_factory=lambda: [
            WorkingShift(start_time="09:00", end_time="13:00"),
            WorkingShift(start_time="14:00", end_time="18:00"),
        ]
    )
    breaks: List[BreakPeriod] = Field(
        default_factory=lambda: [
            BreakPeriod(start_time="13:00", end_time="14:00", title="Lunch Break")
        ]
    )
    duration_minutes: int = Field(default=30, ge=10, le=180)
    buffer_minutes: int = Field(default=10, ge=0, le=60)
    emergency_slots: List[str] = Field(default_factory=list)  # e.g. ["17:00"]
    consultation_types: List[ConsultationType] = Field(
        default_factory=lambda: [ConsultationType.IN_PERSON, ConsultationType.VIDEO]
    )


class DoctorLeave(BaseModel):
    id: Optional[str] = None
    doctor_id: str
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    reason: Optional[str] = "Medical Leave / Vacation"
    created_at: Optional[str] = None


class Doctor(BaseModel):
    name: str
    specialization: str
    experience: int
    fee: int
    bio: Optional[str] = None
    user_id: Optional[str] = None
    consultation_types: List[ConsultationType] = Field(
        default_factory=lambda: [ConsultationType.IN_PERSON, ConsultationType.VIDEO]
    )
    availability: Optional[DoctorAvailability] = None


# --- Slot Generation Models ---
class SlotItem(BaseModel):
    time: str  # e.g. "09:00"
    end_time: str  # e.g. "09:30"
    status: AppointmentStatus = AppointmentStatus.AVAILABLE
    is_emergency: bool = False
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    is_held: bool = False
    held_by_current_user: bool = False
    lock_expires_in_seconds: Optional[int] = None


class UnavailablePeriod(BaseModel):
    start_time: str
    end_time: str
    reason: str


class AvailableSlotsResponse(BaseModel):
    doctor_id: str
    doctor_name: str
    specialization: str
    date: str
    duration_minutes: int
    buffer_minutes: int
    consultation_type: Optional[str] = None
    is_on_leave: bool = False
    leave_reason: Optional[str] = None
    total_available: int = 0
    total_booked: int = 0
    available_slots: List[SlotItem] = Field(default_factory=list)
    booked_slots: List[SlotItem] = Field(default_factory=list)
    unavailable_periods: List[UnavailablePeriod] = Field(default_factory=list)


# --- Redis Slot Locking Schemas ---
class SlotHoldRequest(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "09:00"
    ttl_seconds: Optional[int] = 300


class SlotHoldResponse(BaseModel):
    success: bool
    lock_token: Optional[str] = None
    doctor_id: str
    date: str
    time: str
    expires_in_seconds: Optional[int] = None
    message: str


class SlotReleaseRequest(BaseModel):
    doctor_id: str
    date: str
    time: str
    lock_token: str


# --- Appointment Booking & Lifecycle Models ---
class BookAppointmentRequest(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "09:00"
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    reason: Optional[str] = "General Consultation"
    patient_notes: Optional[str] = None
    lock_token: Optional[str] = None


class Appointment(BaseModel):
    doctor_id: str
    date: str
    time: str
    consultation_type: Optional[ConsultationType] = ConsultationType.IN_PERSON
    reason: Optional[str] = "Consultation"
    patient_notes: Optional[str] = None
    lock_token: Optional[str] = None


class CancelAppointmentRequest(BaseModel):
    reason: str = "Patient requested cancellation"


class RescheduleAppointmentRequest(BaseModel):
    new_date: str
    new_time: str
    new_consultation_type: Optional[ConsultationType] = None
    new_lock_token: Optional[str] = None
    reason: Optional[str] = "Patient rescheduled appointment"


class UpdateAppointmentStatusRequest(BaseModel):
    status: AppointmentStatus
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str
    specialization: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None
    date: str
    time: str
    end_time: Optional[str] = None
    duration_minutes: int = 30
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    reason: Optional[str] = None
    patient_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancellation_reason: Optional[str] = None
    rescheduled_to: Optional[str] = None
    rescheduled_from: Optional[str] = None


# --- Waitlist Models ---
class WaitlistCreateRequest(BaseModel):
    doctor_id: str
    preferred_date: str  # YYYY-MM-DD
    preferred_time: Optional[str] = None  # e.g. "09:00" or None for any slot on that date
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    notes: Optional[str] = None


class WaitlistResponse(BaseModel):
    id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None
    doctor_id: str
    doctor_name: Optional[str] = None
    specialization: Optional[str] = None
    preferred_date: str
    preferred_time: Optional[str] = None
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    status: WaitlistStatus = WaitlistStatus.WAITING
    created_at: str
    notified_at: Optional[str] = None
    claim_deadline: Optional[str] = None
    notes: Optional[str] = None


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


# --- AI Intake & Doctor Matching Models (Phase 3) ---
class UrgencyLevel(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class SupportedSpecialty(str, Enum):
    GENERAL_PHYSICIAN = "General Physician"
    CARDIOLOGIST = "Cardiologist"
    DERMATOLOGIST = "Dermatologist"
    PEDIATRICIAN = "Pediatrician"
    ORTHOPEDIC = "Orthopedic"
    NEUROLOGIST = "Neurologist"
    ENT = "ENT"
    DENTIST = "Dentist"
    GYNECOLOGIST = "Gynecologist"


class AIIntakeRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=1500, description="Patient symptom description or query")
    patient_id: Optional[str] = None
    preferred_date: Optional[str] = None
    consultation_type: Optional[ConsultationType] = ConsultationType.IN_PERSON


class AIStructuredIntake(BaseModel):
    symptoms: List[str] = Field(default_factory=list, description="Extracted distinct clinical symptoms")
    duration: Optional[str] = Field(default="unknown", description="Reported duration of symptoms")
    severity: Optional[str] = Field(default="unknown", description="Reported symptom severity (mild, moderate, severe, unknown)")
    suggested_specialty: str = Field(default="General Physician", description="Controlled medical specialty recommendation")
    urgency: UrgencyLevel = Field(default=UrgencyLevel.ROUTINE, description="Triage urgency classification")
    reasoning: Optional[str] = Field(default=None, description="Non-diagnostic rationale for specialty recommendation")
    emergency_detected: bool = Field(default=False, description="Flag indicating deterministic or LLM emergency detection")
    emergency_advice: Optional[str] = Field(default=None, description="Emergency instructions if red flags detected")


class DoctorMatchItem(BaseModel):
    doctor_id: str
    doctor_name: str
    specialization: str
    experience: int
    fee: int
    rating: float = 4.8
    match_score: int = Field(ge=0, le=100, description="Composite matching score 0-100")
    match_reasons: List[str] = Field(default_factory=list, description="Transparent factors explaining match score")
    available_date: Optional[str] = None
    next_available_slots: List[SlotItem] = Field(default_factory=list, description="Top next available slots for fast booking")


class AIIntakeResponse(BaseModel):
    intake: AIStructuredIntake
    recommended_specialty: str
    matched_doctors: List[DoctorMatchItem] = Field(default_factory=list)
    disclaimer: str = (
        "This evaluation is for intelligent scheduling and triage guidance only. "
        "It does NOT constitute a medical diagnosis or treatment plan. "
        "If you are experiencing severe symptoms, please dial 112 / 911 or visit the nearest emergency facility."
    )
    emergency_alert: Optional[str] = None


class PatientIntakeRecord(BaseModel):
    id: Optional[str] = None
    patient_id: Optional[str] = None
    structured_symptoms: List[str] = Field(default_factory=list)
    duration: Optional[str] = None
    specialty: str
    urgency: str
    emergency_detected: bool = False
    created_at: str


# Legacy / Simple Symptom Check Model
class SymptomCheckRequest(BaseModel):
    symptoms: str = Field(min_length=3, max_length=1000)
