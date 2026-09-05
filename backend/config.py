import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
PREMIUM_AMOUNT_PAISE = int(os.getenv("PREMIUM_AMOUNT_PAISE", "49900"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SLOT_LOCK_TTL_SECONDS = int(os.getenv("SLOT_LOCK_TTL_SECONDS", "300"))  # 5 minutes
DEFAULT_SLOT_DURATION_MINUTES = int(os.getenv("DEFAULT_SLOT_DURATION_MINUTES", "30"))

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# Waitlist Configuration
WAITLIST_CLAIM_WINDOW_MINUTES = int(os.getenv("WAITLIST_CLAIM_WINDOW_MINUTES", "15"))

# Notification Service
NOTIFICATION_BACKEND = os.getenv("NOTIFICATION_BACKEND", "console")  # "console" or "smtp"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "notifications@medibook.health")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
