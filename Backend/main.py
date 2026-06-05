from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId

from database import db
from models import User, Login, Doctor, Appointment
from auth import hash_password, verify_password, create_token, decode_token

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ---------------- REGISTER ----------------
@app.post("/register")
async def register(user: User):

    existing = await db.users.find_one({"email": user.email})
    if existing:
        return {"error": "User already exists"}

    data = {
        "name": user.name,
        "email": user.email,
        "password": hash_password(user.password)
    }

    result = await db.users.insert_one(data)

    return {"message": "registered", "id": str(result.inserted_id)}


# ---------------- LOGIN ----------------
@app.post("/login")
async def login(user: Login):

    db_user = await db.users.find_one({"email": user.email})

    if not db_user:
        raise HTTPException(404, "User not found")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(401, "Wrong password")

    token = create_token({"id": str(db_user["_id"])})

    return {
        "token": token,
        "user_id": str(db_user["_id"])
    }


# ---------------- DOCTORS ----------------
@app.post("/doctor")
async def add_doctor(doc: Doctor):
    result = await db.doctors.insert_one(doc.dict())
    return {"id": str(result.inserted_id)}


@app.get("/doctors")
async def get_doctors():
    docs = []
    async for d in db.doctors.find():
        d["_id"] = str(d["_id"])
        docs.append(d)
    return docs


# ---------------- TOKEN ----------------
def get_user_from_token(credentials: HTTPAuthorizationCredentials):
    token = credentials.credentials
    return decode_token(token)


# ---------------- BOOK APPOINTMENT ----------------
@app.post("/appointment")
async def appointment(
    appo: Appointment,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    user = get_user_from_token(credentials)

    data = appo.dict()
    data["user_id"] = user["id"]

    result = await db.appointments.insert_one(data)

    return {
        "message": "appointment created",
        "id": str(result.inserted_id)
    }


# ---------------- GET APPOINTMENTS (FIXED FINAL) ----------------
@app.get("/appointments")
async def get_appointments(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    user = get_user_from_token(credentials)

    result_list = []

    async for a in db.appointments.find({"user_id": user["id"]}):

        doctor_id = a.get("doctor_id")

        doctor = None

        # SAFE ObjectId handling (FIXED)
        try:
            doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
        except:
            doctor = await db.doctors.find_one({"_id": doctor_id})

        result_list.append({
            "_id": str(a["_id"]),
            "doctor_id": doctor_id,
            "doctor_name": doctor["name"] if doctor else "Unknown Doctor",
            "specialization": doctor["specialization"] if doctor else "N/A",
            "date": a.get("date"),
            "time": a.get("time", "Not set")
        })

    return result_list