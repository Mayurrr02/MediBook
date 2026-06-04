from fastapi import FastAPI, HTTPException, Header
from database import db
from models import User, Login, Doctor, Appointment
from auth import hash_password, verify_password, create_token, decode_token
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    return {
        "message": "User registered",
        "id": str(result.inserted_id)
    }


# ---------------- LOGIN ----------------
@app.post("/login")
async def login(user: Login):

    db_user = await db.users.find_one({"email": user.email})

    if not db_user:
        raise HTTPException(404, "User not found")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(401, "Wrong password")

    token = create_token({"id": str(db_user["_id"])})

    return {"token": token}


# ---------------- ADD DOCTOR ----------------
@app.post("/doctor")
async def add_doctor(doc: Doctor):

    result = await db.doctors.insert_one(doc.dict())

    return {"id": str(result.inserted_id)}


# ---------------- GET DOCTORS ----------------
@app.get("/doctors")
async def get_doctors():

    docs = []
    async for d in db.doctors.find():
        d["_id"] = str(d["_id"])
        docs.append(d)

    return docs


# ---------------- BOOK APPOINTMENT ----------------
@app.post("/appointment")
async def appointment(appo: Appointment, authorization: str = Header(None)):

    print("HEADER RECEIVED:", authorization)

    if not authorization:
        return {"error": "Missing token"}

    try:
        scheme, token = authorization.split()
        print("TOKEN:", token)

        user = decode_token(token)
        print("USER:", user)

    except Exception as e:
        print("ERROR:", str(e))
        return {"error": "Invalid token", "details": str(e)}

    data = appo.dict()
    data["user_id"] = user["id"]

    result = await db.appointments.insert_one(data)

    return {
        "message": "appointment created",
        "id": str(result.inserted_id)
    }
# ---------------- GET APPOINTMENTS ----------------
@app.get("/appointments")
async def get_appointments(authorization: str = Header(None)):

    token = authorization.split(" ")[1]
    user = decode_token(token)

    data = []

    async for a in db.appointments.find({"user_id": user["id"]}):
        a["_id"] = str(a["_id"])
        data.append(a)

    return data