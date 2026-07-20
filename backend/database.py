from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client.medibook


async def init_indexes():
    """Call once at startup. Prevents duplicate-email race conditions and
    speeds up the lookups the app does on every request."""
    await db.users.create_index("email", unique=True)
    await db.appointments.create_index([("doctor_id", 1), ("date", 1), ("time", 1)])
    await db.appointments.create_index("user_id")
