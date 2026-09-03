import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo
from config import MONGO_URI

_client_instance = None
_db_instance = None
_bound_loop = None


def get_db():
    """Returns database instance attached to the current running event loop."""
    global _client_instance, _db_instance, _bound_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _db_instance is None or _bound_loop is not current_loop:
        try:
            _client_instance = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            _db_instance = _client_instance.medibook
            _bound_loop = current_loop
        except Exception:
            _client_instance = AsyncIOMotorClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=1000)
            _db_instance = _client_instance.medibook
            _bound_loop = current_loop

    return _db_instance


class DatabaseProxy:
    """Proxy that dynamically delegates attribute access (e.g. db.users) to current loop DB instance."""
    def __getattr__(self, name):
        return getattr(get_db(), name)

    def __getitem__(self, name):
        return get_db()[name]


db = DatabaseProxy()


async def init_indexes():
    """
    Call once at startup. Creates essential indexes for high performance
    and data integrity across users, appointments, doctor schedules, waitlists, and audit logs.
    """
    try:
        active_db = get_db()
        # Users
        await active_db.users.create_index("email", unique=True)
        await active_db.users.create_index("role")

        # Doctors
        await active_db.doctors.create_index("specialization")

        # Doctor Schedules
        await active_db.doctor_schedules.create_index("doctor_id", unique=True)

        # Appointments
        await active_db.appointments.create_index(
            [("doctor_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING), ("time", pymongo.ASCENDING)]
        )
        await active_db.appointments.create_index("user_id")
        await active_db.appointments.create_index("doctor_id")
        await active_db.appointments.create_index("status")
        await active_db.appointments.create_index([("date", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])

        # Waitlists
        await active_db.waitlists.create_index(
            [("doctor_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING), ("time", pymongo.ASCENDING), ("status", pymongo.ASCENDING)]
        )
        await active_db.waitlists.create_index("user_id")

        # Audit Logs
        await active_db.audit_logs.create_index([("timestamp", pymongo.DESCENDING)])
        await active_db.audit_logs.create_index("action")
        await active_db.audit_logs.create_index("user_id")
    except Exception as e:
        print(f"[Warning] Failed to initialize some MongoDB indexes: {e}")
