import datetime
import logging
from celery_app import celery_app, run_async
from database import db
from models import AppointmentStatus
from services.notification_service import NotificationService
from services.scheduling_service import parse_time

logger = logging.getLogger("medibook.tasks.reminders")


async def _async_send_24h_reminders():
    tomorrow_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    cursor = db.appointments.find({
        "date": tomorrow_date,
        "status": AppointmentStatus.CONFIRMED.value,
        "reminder_24h_sent": {"$ne": True},
    })

    count = 0
    async for appt in cursor:
        patient_email = appt.get("patient_email")
        if patient_email:
            NotificationService.notify_appointment_reminder(
                patient_email=patient_email,
                patient_name=appt.get("patient_name", "Patient"),
                doctor_name=appt.get("doctor_name", "Doctor"),
                date=appt.get("date"),
                time=appt.get("time"),
                reminder_type="24h",
            )
            await db.appointments.update_one(
                {"_id": appt["_id"]},
                {"$set": {"reminder_24h_sent": True}}
            )
            count += 1

    logger.info(f"Sent 24-hour reminders for {count} appointments on {tomorrow_date}.")
    return {"reminders_sent": count, "date": tomorrow_date}


async def _async_send_1h_reminders():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    now_dt = datetime.datetime.now()
    window_start = (now_dt + datetime.timedelta(minutes=45)).time()
    window_end = (now_dt + datetime.timedelta(minutes=75)).time()

    cursor = db.appointments.find({
        "date": today_str,
        "status": AppointmentStatus.CONFIRMED.value,
        "reminder_1h_sent": {"$ne": True},
    })

    count = 0
    async for appt in cursor:
        try:
            t_obj = parse_time(appt.get("time", ""))
            if window_start <= t_obj <= window_end:
                patient_email = appt.get("patient_email")
                if patient_email:
                    NotificationService.notify_appointment_reminder(
                        patient_email=patient_email,
                        patient_name=appt.get("patient_name", "Patient"),
                        doctor_name=appt.get("doctor_name", "Doctor"),
                        date=appt.get("date"),
                        time=appt.get("time"),
                        reminder_type="1h",
                    )
                    await db.appointments.update_one(
                        {"_id": appt["_id"]},
                        {"$set": {"reminder_1h_sent": True}}
                    )
                    count += 1
        except Exception as e:
            logger.warning(f"Error parsing time for 1h reminder: {e}")

    logger.info(f"Sent 1-hour reminders for {count} appointments today.")
    return {"reminders_sent": count}


@celery_app.task(name="tasks.reminders.send_24h_reminders_task")
def send_24h_reminders_task():
    return run_async(_async_send_24h_reminders())


@celery_app.task(name="tasks.reminders.send_1h_reminders_task")
def send_1h_reminders_task():
    return run_async(_async_send_1h_reminders())
