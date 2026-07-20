from fastapi import APIRouter, HTTPException

from database import db
from models import UserRegister, Login
from auth import hash_password, verify_password, create_token

router = APIRouter(tags=["auth"])


@router.post("/register")
async def register(user: UserRegister):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(409, "User already exists")

    data = {
        "name": user.name,
        "email": user.email,
        "password": hash_password(user.password),
        "is_admin": False,
        "is_premium": False,
        "premium_since": None,
    }
    result = await db.users.insert_one(data)
    return {"message": "registered", "id": str(result.inserted_id)}


@router.post("/login")
async def login(user: Login):
    db_user = await db.users.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        # Same error for both cases - don't leak which one was wrong.
        raise HTTPException(401, "Invalid email or password")

    token = create_token({"id": str(db_user["_id"])})
    return {
        "token": token,
        "user_id": str(db_user["_id"]),
        "name": db_user["name"],
        "is_premium": db_user.get("is_premium", False),
        "is_admin": db_user.get("is_admin", False),
    }
