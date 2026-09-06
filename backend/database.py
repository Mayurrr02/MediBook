import asyncio
import copy
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo
from config import MONGO_URI

_client_instance = None
_db_instance = None
_bound_loop = None
_use_memory_db = False


class MockInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class MockUpdateResult:
    def __init__(self, matched_count=1, modified_count=1):
        self.matched_count = matched_count
        self.modified_count = modified_count


class MockDeleteResult:
    def __init__(self, deleted_count=1):
        self.deleted_count = deleted_count


class MockAsyncCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, key, direction=1):
        reverse = (direction == -1 or direction == pymongo.DESCENDING)
        self._docs.sort(key=lambda d: str(d.get(key, "")), reverse=reverse)
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _matches_filter(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    if not query:
        return True

    if "$or" in query:
        if not any(_matches_filter(doc, sub_q) for sub_q in query["$or"]):
            return False

    for k, v in query.items():
        if k == "$or":
            continue
        doc_val = doc.get(k)

        if k == "_id":
            if isinstance(v, ObjectId):
                if str(doc_val) != str(v):
                    return False
            elif str(doc_val) != str(v):
                return False
            continue

        if isinstance(v, dict):
            for op, target_val in v.items():
                if op == "$in":
                    if doc_val not in target_val and str(doc_val) not in [str(x) for x in target_val]:
                        return False
                elif op == "$lt":
                    if doc_val is None or str(doc_val) >= str(target_val):
                        return False
                elif op == "$gt":
                    if doc_val is None or str(doc_val) <= str(target_val):
                        return False
                elif op == "$lte":
                    if doc_val is None or str(doc_val) > str(target_val):
                        return False
                elif op == "$gte":
                    if doc_val is None or str(doc_val) < str(target_val):
                        return False
                elif op == "$ne":
                    if doc_val == target_val or str(doc_val) == str(target_val):
                        return False
        else:
            if str(doc_val) != str(v):
                return False

    return True


class MockAsyncCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: List[Dict[str, Any]] = []

    async def create_index(self, *args, **kwargs):
        return "mock_index"

    async def count_documents(self, filter: Optional[Dict[str, Any]] = None) -> int:
        filter = filter or {}
        return sum(1 for d in self._docs if _matches_filter(d, filter))

    async def insert_one(self, document: Dict[str, Any]):
        doc_copy = copy.deepcopy(document)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        self._docs.append(doc_copy)
        return MockInsertResult(doc_copy["_id"])

    async def find_one(self, filter: Optional[Dict[str, Any]] = None):
        filter = filter or {}
        for d in self._docs:
            if _matches_filter(d, filter):
                return copy.deepcopy(d)
        return None

    def find(self, filter: Optional[Dict[str, Any]] = None):
        filter = filter or {}
        matched = [copy.deepcopy(d) for d in self._docs if _matches_filter(d, filter)]
        return MockAsyncCursor(matched)

    async def update_one(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        for idx, d in enumerate(self._docs):
            if _matches_filter(d, filter):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        d[k] = copy.deepcopy(v)
                return MockUpdateResult(1, 1)

        if upsert:
            new_doc = copy.deepcopy(filter)
            if "$set" in update:
                new_doc.update(copy.deepcopy(update["$set"]))
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self._docs.append(new_doc)
            return MockUpdateResult(0, 1)

        return MockUpdateResult(0, 0)

    async def delete_one(self, filter: Dict[str, Any]):
        for idx, d in enumerate(self._docs):
            if _matches_filter(d, filter):
                del self._docs[idx]
                return MockDeleteResult(1)
        return MockDeleteResult(0)

    async def delete_many(self, filter: Dict[str, Any]):
        original_count = len(self._docs)
        self._docs = [d for d in self._docs if not _matches_filter(d, filter)]
        return MockDeleteResult(original_count - len(self._docs))


class MockAsyncDatabase:
    def __init__(self):
        self._collections: Dict[str, MockAsyncCollection] = {}

    def __getattr__(self, name: str) -> MockAsyncCollection:
        if name not in self._collections:
            self._collections[name] = MockAsyncCollection(name)
        return self._collections[name]

    def __getitem__(self, name: str) -> MockAsyncCollection:
        return self.__getattr__(name)

    async def command(self, cmd: str, *args, **kwargs):
        if cmd == "ping":
            return {"ok": 1}
        return {}


_memory_db_instance = MockAsyncDatabase()


def get_db():
    """Returns real Mongo DB client or fallback in-memory DB when Mongo server is offline."""
    global _client_instance, _db_instance, _bound_loop, _use_memory_db

    if _use_memory_db:
        return _memory_db_instance

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _db_instance is None or _bound_loop is not current_loop:
        try:
            _client_instance = AsyncIOMotorClient(
                MONGO_URI,
                serverSelectionTimeoutMS=500,
                connectTimeoutMS=500,
            )
            _db_instance = _client_instance.medibook
            _bound_loop = current_loop
        except Exception:
            _use_memory_db = True
            return _memory_db_instance

    return _db_instance


class DatabaseProxy:
    """Proxy that dynamically delegates attribute access (e.g. db.users) to active DB instance."""
    def __getattr__(self, name):
        try:
            return getattr(get_db(), name)
        except Exception:
            return getattr(_memory_db_instance, name)

    def __getitem__(self, name):
        try:
            return get_db()[name]
        except Exception:
            return _memory_db_instance[name]


db = DatabaseProxy()


async def init_indexes():
    """
    Creates essential indexes for doctor scheduling, leave management,
    appointment queries, and double-booking prevention.
    """
    try:
        active_db = get_db()
        # Users
        await active_db.users.create_index("email", unique=True)
        await active_db.users.create_index("role")

        # Doctors
        await active_db.doctors.create_index("specialization")
        await active_db.doctors.create_index("user_id")

        # Doctor Availability
        await active_db.doctor_availabilities.create_index("doctor_id", unique=True)

        # Doctor Leaves
        await active_db.doctor_leaves.create_index(
            [("doctor_id", pymongo.ASCENDING), ("start_date", pymongo.ASCENDING), ("end_date", pymongo.ASCENDING)]
        )

        # Appointments
        await active_db.appointments.create_index(
            [("doctor_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING), ("status", pymongo.ASCENDING)]
        )
        await active_db.appointments.create_index(
            [("doctor_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING), ("time", pymongo.ASCENDING)]
        )
        await active_db.appointments.create_index("patient_id")
        await active_db.appointments.create_index("user_id")
        await active_db.appointments.create_index("status")
        await active_db.appointments.create_index([("date", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
    except Exception as e:
        print(f"[Warning] Failed to initialize some MongoDB indexes: {e}")


async def seed_default_doctors():
    """
    Seeds initial certified doctors with realistic availability schedules
    if the doctors collection is empty.
    """
    try:
        active_db = get_db()
        count = await active_db.doctors.count_documents({})
        if count > 0:
            return

        default_doctors = [
            {
                "name": "Sarah Jenkins",
                "email": "dr.jenkins@medibook.health",
                "specialization": "Cardiology",
                "experience": 12,
                "fee": 500,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4],  # Mon-Fri
                    "shifts": [
                        {"start_time": "09:00", "end_time": "13:00"},
                        {"start_time": "14:00", "end_time": "18:00"},
                    ],
                    "breaks": [
                        {"start_time": "13:00", "end_time": "14:00", "reason": "Lunch Break"}
                    ],
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 10,
                    "emergency_slots_count": 2,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
            {
                "name": "David Chen",
                "email": "dr.chen@medibook.health",
                "specialization": "Neurology",
                "experience": 15,
                "fee": 750,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4],
                    "shifts": [
                        {"start_time": "09:00", "end_time": "12:00"},
                        {"start_time": "13:30", "end_time": "17:30"},
                    ],
                    "breaks": [
                        {"start_time": "12:00", "end_time": "13:30", "reason": "Rounds & Lunch"}
                    ],
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 15,
                    "emergency_slots_count": 1,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
            {
                "name": "Priya Sharma",
                "email": "dr.sharma@medibook.health",
                "specialization": "Pediatrics",
                "experience": 9,
                "fee": 400,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4, 5],  # Mon-Sat
                    "shifts": [
                        {"start_time": "10:00", "end_time": "14:00"},
                        {"start_time": "15:00", "end_time": "19:00"},
                    ],
                    "breaks": [
                        {"start_time": "14:00", "end_time": "15:00", "reason": "Lunch Break"}
                    ],
                    "slot_duration_minutes": 20,
                    "buffer_minutes": 10,
                    "emergency_slots_count": 2,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
            {
                "name": "Marcus Vance",
                "email": "dr.vance@medibook.health",
                "specialization": "Dermatology",
                "experience": 10,
                "fee": 600,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4],
                    "shifts": [
                        {"start_time": "08:30", "end_time": "12:30"},
                        {"start_time": "13:30", "end_time": "16:30"},
                    ],
                    "breaks": [
                        {"start_time": "12:30", "end_time": "13:30", "reason": "Lunch Break"}
                    ],
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 10,
                    "emergency_slots_count": 1,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
            {
                "name": "Elena Rostova",
                "email": "dr.rostova@medibook.health",
                "specialization": "General Medicine",
                "experience": 8,
                "fee": 350,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4, 5],
                    "shifts": [
                        {"start_time": "09:00", "end_time": "13:00"},
                        {"start_time": "14:00", "end_time": "18:00"},
                    ],
                    "breaks": [
                        {"start_time": "13:00", "end_time": "14:00", "reason": "Lunch Break"}
                    ],
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 10,
                    "emergency_slots_count": 2,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
            {
                "name": "James Wilson",
                "email": "dr.wilson@medibook.health",
                "specialization": "Orthopedics",
                "experience": 14,
                "fee": 700,
                "availability": {
                    "working_days": [0, 1, 2, 3, 4],
                    "shifts": [
                        {"start_time": "09:00", "end_time": "13:00"},
                        {"start_time": "14:00", "end_time": "17:30"},
                    ],
                    "breaks": [
                        {"start_time": "13:00", "end_time": "14:00", "reason": "Lunch Break"}
                    ],
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 15,
                    "emergency_slots_count": 1,
                    "supported_consultations": ["IN_PERSON", "VIDEO"],
                },
            },
        ]

        for d_data in default_doctors:
            avail_data = d_data.pop("availability")
            insert_res = await active_db.doctors.insert_one(d_data)
            doc_id = str(insert_res.inserted_id)
            avail_data["doctor_id"] = doc_id
            await active_db.doctor_availabilities.insert_one(avail_data)

        print("[Seed] Successfully seeded 6 default doctors and availability schedules.")
    except Exception as e:
        print(f"[Seed Warning] Failed to auto-seed default doctors: {e}")

