import pytest
import datetime
from bson import ObjectId
from fastapi import HTTPException
from database import db
from models import (
    WaitlistCreateRequest,
    WaitlistStatus,
    ConsultationType,
    AppointmentStatus,
)
from services.waitlist_service import (
    join_waitlist,
    list_patient_waitlists,
    cancel_waitlist_entry,
    process_waitlist_on_cancellation,
    claim_waitlist_slot,
    expire_stale_waitlist_claims,
)
from services.appointment_service import book_appointment, cancel_appointment
from services.lock_service import force_release_slot_lock


@pytest.mark.asyncio
async def test_waitlist_lifecycle_and_auto_promotion():
    doc_res = await db.doctors.insert_one({
        "name": "Dr. Waitlist Specialist",
        "specialization": "Cardiology",
        "experience": 10,
        "fee": 500,
    })
    doctor_id = str(doc_res.inserted_id)

    patient_1 = {"_id": "60c72b2f9b1d8b2bad000011", "name": "Patient One", "email": "p1@test.com"}
    patient_2 = {"_id": "60c72b2f9b1d8b2bad000022", "name": "Patient Two (Waitlist)", "email": "p2@test.com"}
    patient_3 = {"_id": "60c72b2f9b1d8b2bad000033", "name": "Patient Three (Waitlist 2)", "email": "p3@test.com"}

    test_date = "2026-12-14"  # Monday
    test_time = "11:00"

    await force_release_slot_lock(doctor_id, test_date, test_time)

    # 1. Patient 1 books the slot
    appt = await book_appointment(
        doctor_id=doctor_id,
        date=test_date,
        time_slot=test_time,
        user=patient_1,
        consultation_type=ConsultationType.IN_PERSON,
    )
    appt_id = appt["id"]

    # 2. Patient 2 joins the waitlist for this slot
    req_w2 = WaitlistCreateRequest(
        doctor_id=doctor_id,
        preferred_date=test_date,
        preferred_time=test_time,
        consultation_type=ConsultationType.IN_PERSON,
        notes="Need early consultation if available",
    )
    w2_res = await join_waitlist(req_w2, patient_2)
    assert w2_res["status"] == WaitlistStatus.WAITING.value
    w2_id = w2_res["id"]

    # Patient 2 joining again should raise 409 Conflict
    with pytest.raises(HTTPException) as exc_dup:
        await join_waitlist(req_w2, patient_2)
    assert exc_dup.value.status_code == 409

    # 3. Patient 3 joins the waitlist as well (2nd in FIFO queue)
    req_w3 = WaitlistCreateRequest(
        doctor_id=doctor_id,
        preferred_date=test_date,
        preferred_time=test_time,
        consultation_type=ConsultationType.IN_PERSON,
    )
    w3_res = await join_waitlist(req_w3, patient_3)
    w3_id = w3_res["id"]

    # Check Patient 2's waitlist history
    p2_waitlists = await list_patient_waitlists(patient_2["_id"])
    assert len(p2_waitlists) >= 1
    assert p2_waitlists[0]["status"] == WaitlistStatus.WAITING.value

    # 4. Patient 1 cancels their appointment -> triggers AUTOMATIC waitlist promotion for Patient 2!
    cancel_res = await cancel_appointment(
        appointment_id=appt_id,
        user=patient_1,
        reason="Unable to attend",
    )
    assert cancel_res["status"] == AppointmentStatus.CANCELLED.value

    # 5. Verify Patient 2 is now NOTIFIED with a claim deadline and temporary lock
    w2_doc = await db.waitlists.find_one({"_id": ObjectId(w2_id)})
    assert w2_doc["status"] == WaitlistStatus.NOTIFIED.value
    assert w2_doc["notified_at"] is not None
    assert w2_doc["claim_deadline"] is not None

    # Patient 3 is still WAITING in line
    w3_doc = await db.waitlists.find_one({"_id": ObjectId(w3_id)})
    assert w3_doc["status"] == WaitlistStatus.WAITING.value

    # 6. Patient 2 claims their offered slot
    claim_res = await claim_waitlist_slot(
        waitlist_id=w2_id,
        user=patient_2,
        reason="Claimed from waitlist",
    )
    assert "claimed and confirmed successfully" in claim_res["message"].lower()

    # Verify Patient 2's waitlist is now BOOKED and appointment is created
    w2_doc_after = await db.waitlists.find_one({"_id": ObjectId(w2_id)})
    assert w2_doc_after["status"] == WaitlistStatus.BOOKED.value

    new_appt_id = claim_res["appointment"]["id"]
    new_appt = await db.appointments.find_one({"_id": ObjectId(new_appt_id)})
    assert new_appt["status"] == AppointmentStatus.CONFIRMED.value
    assert str(new_appt["patient_id"]) == patient_2["_id"]

    # Clean up
    await db.doctors.delete_one({"_id": ObjectId(doctor_id)})
    await db.appointments.delete_many({"doctor_id": doctor_id})
    await db.waitlists.delete_many({"doctor_id": doctor_id})
    await force_release_slot_lock(doctor_id, test_date, test_time)
