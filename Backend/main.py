from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import db
from models import User, Login, Doctor, Appointment
from auth import hash_password, verify_password, create_token, decode_token

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SECURITY (THIS FIXES SWAGGER AUTH BUTTON)
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


# ---------------- TOKEN HELPER ----------------
def get_user_from_token(credentials: HTTPAuthorizationCredentials):

    token = credentials.credentials
    return decode_token(token)


# ---------------- APPOINTMENT ----------------
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


# ---------------- GET APPOINTMENTS ----------------
@app.get("/appointments")
async def get_appointments(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    user = get_user_from_token(credentials)

    data = []

    async for a in db.appointments.find({"user_id": user["id"]}):
        a["_id"] = str(a["_id"])
        data.append(a)

    return data