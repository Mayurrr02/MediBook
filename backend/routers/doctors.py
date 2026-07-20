from fastapi import APIRouter, Depends

from database import db
from models import Doctor
from dependencies import require_admin

router = APIRouter(tags=["doctors"])


@router.post("/doctor")
async def add_doctor(doc: Doctor, admin=Depends(require_admin)):
    result = await db.doctors.insert_one(doc.dict())
    return {"id": str(result.inserted_id)}


@router.get("/doctors")
async def get_doctors():
    docs = []
    async for d in db.doctors.find():
        d["_id"] = str(d["_id"])
        docs.append(d)
    return docs
