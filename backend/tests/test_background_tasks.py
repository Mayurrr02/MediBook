import pytest
import datetime
from database import db
from models import AppointmentStatus, WaitlistStatus
from tasks.reminders import _async_send_24h_reminders, _async_send_1h_reminders
from services.waitlist_service import expire_stale_waitlist_claims


@pytest.mark.asyncio
async def test_24h_and_1h_reminders_tasks():
    tomorrow_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today_date = datetime.date.today().strftime("%Y-%m-%d")

    # Insert test appointment for tomorrow
    await db.appointments.insert_one({
        "doctor_name": "Dr. Reminder Test",
        "patient_name": "Test Patient",
        "patient_email": "patient_reminder@test.com",
        "date": tomorrow_date,
        "time": "10:00",
        "status": AppointmentStatus.CONFIRMED.value,
        "reminder_24h_sent": False,
    })

    # Run 24h reminders task
    res_24h = await _async_send_24h_reminders()
    assert res_24h["reminders_sent"] >= 1

    # Insert test appointment for today in the 1h window
    now_plus_50 = (datetime.datetime.now() + datetime.timedelta(minutes=50)).strftime("%H:%M")
    await db.appointments.insert_one({
        "doctor_name": "Dr. Reminder Test 2",
        "patient_name": "Test Patient 2",
        "patient_email": "patient_reminder2@test.com",
        "date": today_date,
        "time": now_plus_50,
        "status": AppointmentStatus.CONFIRMED.value,
        "reminder_1h_sent": False,
    })

    res_1h = await _async_send_1h_reminders()
    assert res_1h["reminders_sent"] >= 1

    # Clean up
    await db.appointments.delete_many({"patient_email": {"$in": ["patient_reminder@test.com", "patient_reminder2@test.com"]}})


@pytest.mark.asyncio
async def test_waitlist_claim_expiration_task():
    past_deadline = (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat()
    await db.waitlists.insert_one({
        "patient_id": "60c72b2f9b1d8b2bad000999",
        "patient_name": "Expired Patient",
        "patient_email": "expired@test.com",
        "doctor_id": "60c72b2f9b1d8b2bad000888",
        "preferred_date": "2026-12-20",
        "preferred_time": "14:00",
        "status": WaitlistStatus.NOTIFIED.value,
        "claim_deadline": past_deadline,
    })

    await expire_stale_waitlist_claims()

    doc = await db.waitlists.find_one({"patient_email": "expired@test.com"})
    assert doc["status"] == WaitlistStatus.EXPIRED.value

    # Clean up
    await db.waitlists.delete_many({"patient_email": "expired@test.com"})
