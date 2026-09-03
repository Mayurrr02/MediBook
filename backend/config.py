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

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SLOT_LOCK_TTL_SECONDS = int(os.getenv("SLOT_LOCK_TTL_SECONDS", "300"))
DEFAULT_SLOT_DURATION_MINUTES = int(os.getenv("DEFAULT_SLOT_DURATION_MINUTES", "30"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
