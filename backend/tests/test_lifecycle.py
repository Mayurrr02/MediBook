import pytest
from fastapi import HTTPException
from models import AppointmentStatus
from services.appointment_service import _validate_transition, VALID_TRANSITIONS


def test_valid_state_transitions():
    # PENDING -> CONFIRMED
    _validate_transition(AppointmentStatus.PENDING_CONFIRMATION, AppointmentStatus.CONFIRMED)

    # PENDING -> CANCELLED
    _validate_transition(AppointmentStatus.PENDING_CONFIRMATION, AppointmentStatus.CANCELLED)

    # CONFIRMED -> IN_PROGRESS
    _validate_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS)

    # CONFIRMED -> COMPLETED
    _validate_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED)

    # CONFIRMED -> CANCELLED
    _validate_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED)

    # CONFIRMED -> RESCHEDULED
    _validate_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED)

    # CONFIRMED -> NO_SHOW
    _validate_transition(AppointmentStatus.CONFIRMED, AppointmentStatus.NO_SHOW)

    # IN_PROGRESS -> COMPLETED
    _validate_transition(AppointmentStatus.IN_PROGRESS, AppointmentStatus.COMPLETED)


def test_invalid_state_transitions():
    # Completed cannot be cancelled or confirmed
    with pytest.raises(HTTPException) as exc1:
        _validate_transition(AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED)
    assert exc1.value.status_code == 400

    # Cancelled cannot be revived to confirmed
    with pytest.raises(HTTPException) as exc2:
        _validate_transition(AppointmentStatus.CANCELLED, AppointmentStatus.CONFIRMED)
    assert exc2.value.status_code == 400

    # Rescheduled cannot be changed to in-progress
    with pytest.raises(HTTPException) as exc3:
        _validate_transition(AppointmentStatus.RESCHEDULED, AppointmentStatus.IN_PROGRESS)
    assert exc3.value.status_code == 400

    # No show cannot be completed
    with pytest.raises(HTTPException) as exc4:
        _validate_transition(AppointmentStatus.NO_SHOW, AppointmentStatus.COMPLETED)
    assert exc4.value.status_code == 400
