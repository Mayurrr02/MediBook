import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any

from config import (
    NOTIFICATION_BACKEND,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_FROM,
)

logger = logging.getLogger("medibook.notifications")


class NotificationService:
    """
    Abstracted notification dispatch service for email, reminders, and alerts.
    Operates safely in console mode during development / testing without hardcoded credentials.
    """

    @classmethod
    def send_email(cls, to_email: str, subject: str, body_text: str, html_body: Optional[str] = None) -> bool:
        if not to_email:
            return False

        if NOTIFICATION_BACKEND == "smtp" and SMTP_USER and SMTP_PASS:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = SMTP_FROM
                msg["To"] = to_email

                msg.attach(MIMEText(body_text, "plain"))
                if html_body:
                    msg.attach(MIMEText(html_body, "html"))

                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_FROM, [to_email], msg.as_string())
                logger.info(f"Email sent via SMTP to {to_email}: {subject}")
                return True
            except Exception as e:
                logger.error(f"Failed to send email via SMTP to {to_email}: {e}")
                return False
        else:
            # Console logger fallback
            logger.info(f"[NOTIFICATION - {NOTIFICATION_BACKEND.upper()}] To: {to_email} | Subject: {subject} | Content: {body_text[:100]}...")
            return True

    @classmethod
    def notify_appointment_confirmation(
        cls,
        patient_email: str,
        patient_name: str,
        doctor_name: str,
        date: str,
        time: str,
        consultation_type: str,
        appointment_id: str
    ) -> bool:
        subject = f"Appointment Confirmed: Dr. {doctor_name} on {date}"
        body = (
            f"Dear {patient_name},\n\n"
            f"Your appointment with Dr. {doctor_name} has been confirmed.\n"
            f"Date: {date}\n"
            f"Time: {time}\n"
            f"Consultation Type: {consultation_type}\n"
            f"Appointment ID: {appointment_id}\n\n"
            f"Thank you for choosing MediBook."
        )
        return cls.send_email(patient_email, subject, body)

    @classmethod
    def notify_appointment_reminder(
        cls,
        patient_email: str,
        patient_name: str,
        doctor_name: str,
        date: str,
        time: str,
        reminder_type: str = "24h"
    ) -> bool:
        timeframe = "tomorrow" if reminder_type == "24h" else "in 1 hour"
        subject = f"Upcoming Appointment Reminder ({timeframe}): Dr. {doctor_name}"
        body = (
            f"Dear {patient_name},\n\n"
            f"This is a reminder that you have an upcoming appointment with Dr. {doctor_name} {timeframe} at {time} on {date}.\n\n"
            f"Please arrive or log in 5 minutes early."
        )
        return cls.send_email(patient_email, subject, body)

    @classmethod
    def notify_waitlist_promoted(
        cls,
        patient_email: str,
        patient_name: str,
        doctor_name: str,
        date: str,
        time: str,
        claim_deadline: str
    ) -> bool:
        subject = f"Slot Available! You have been promoted from the Waitlist for Dr. {doctor_name}"
        body = (
            f"Dear {patient_name},\n\n"
            f"Good news! A slot has opened up with Dr. {doctor_name} on {date} at {time}.\n"
            f"You have until {claim_deadline} to claim this slot before it is offered to the next waitlisted patient.\n\n"
            f"Log in to your MediBook dashboard now to confirm your booking."
        )
        return cls.send_email(patient_email, subject, body)

    @classmethod
    def notify_cancellation(
        cls,
        patient_email: str,
        patient_name: str,
        doctor_name: str,
        date: str,
        time: str,
        reason: str
    ) -> bool:
        subject = f"Appointment Cancelled: Dr. {doctor_name} on {date}"
        body = (
            f"Dear {patient_name},\n\n"
            f"Your appointment with Dr. {doctor_name} on {date} at {time} has been cancelled.\n"
            f"Reason: {reason}\n\n"
            f"You can log in to MediBook anytime to reschedule."
        )
        return cls.send_email(patient_email, subject, body)
