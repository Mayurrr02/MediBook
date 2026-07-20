from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from auth import decode_token
from database import db

security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

    try:
        user = await db.users.find_one({"_id": ObjectId(payload["id"])})
    except InvalidId:
        raise HTTPException(401, "Invalid token")

    if not user:
        raise HTTPException(401, "User not found")

    user["_id"] = str(user["_id"])
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin access required")
    return user


async def require_premium(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_premium"):
        raise HTTPException(403, "This is a premium feature — upgrade to unlock")
    return user
