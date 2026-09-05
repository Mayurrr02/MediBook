import pytest
from fastapi import HTTPException
from models import AppointmentStatus
from services.appointment_service import validate_state_transition, VALID_TRANSITIONS


def test_valid_lifecycle_transitions():
    # HELD -> CONFIRMED, CANCELLED, EXPIRED
    validate_state_transition(AppointmentStatus.HELD, AppointmentStatus.CONFIRMED)
    validate_state_transition(AppointmentStatus.HELD, AppointmentStatus.CANCELLED)
    validate_state_transition(AppointmentStatus.HELD, AppointmentStatus.EXPIRED)

    # CONFIRMED -> COMPLETED, CANCELLED, NO_SHOW
    validate_state_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED)
    validate_state_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED)
    validate_state_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.NO_SHOW)


def test_invalid_lifecycle_transitions():
    # CANCELLED -> COMPLETED (Not allowed)
    with pytest.raises(HTTPException) as exc1:
        validate_state_transition(AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED)
    assert exc1.value.status_code == 400
    assert "Invalid state transition" in exc1.value.detail

    # COMPLETED -> CANCELLED (Terminal state, cannot cancel after completion)
    with pytest.raises(HTTPException) as exc2:
        validate_state_transition(AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED)
    assert exc2.value.status_code == 400

    # NO_SHOW -> CONFIRMED (Terminal state)
    with pytest.raises(HTTPException) as exc3:
        validate_state_transition(AppointmentStatus.NO_SHOW, AppointmentStatus.CONFIRMED)
    assert exc3.value.status_code == 400

    # EXPIRED -> CONFIRMED (Terminal state)
    with pytest.raises(HTTPException) as exc4:
        validate_state_transition(AppointmentStatus.EXPIRED, AppointmentStatus.CONFIRMED)
    assert exc4.value.status_code == 400
