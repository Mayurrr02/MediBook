from typing import List, Optional
from fastapi import APIRouter, Request, Depends, Header
from jose import JWTError

from auth import decode_token
from database import db
from models import (
    AIIntakeRequest,
    AIIntakeResponse,
    SupportedSpecialty,
    PatientIntakeRecord,
)
from services.ai_intake_service import process_patient_intake

router = APIRouter(tags=["ai_intake"])


def get_optional_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Helper to extract user ID from optional Bearer token without raising 401."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = decode_token(token)
        return str(payload.get("id") or payload.get("_id") or "")
    except (JWTError, Exception):
        return None


@router.post("/api/v1/ai/intake", response_model=AIIntakeResponse)
@router.post("/ai/intake", response_model=AIIntakeResponse)
async def submit_ai_intake(
    req: AIIntakeRequest,
    request: Request,
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Analyzes patient symptom descriptions, detects acute red-flags, extracts structured
    symptoms, maps to a controlled specialty, and returns ranked doctor matches with next slots.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    if user_id and not req.patient_id:
        req.patient_id = user_id

    return await process_patient_intake(request=req, client_ip=client_ip)


@router.get("/api/v1/ai/specialties", response_model=List[str])
@router.get("/ai/specialties", response_model=List[str])
async def get_supported_specialties():
    """Returns the controlled taxonomy of supported medical specialties."""
    return [s.value for s in SupportedSpecialty]


@router.get("/api/v1/ai/intakes/me", response_model=List[PatientIntakeRecord])
@router.get("/ai/intakes/me", response_model=List[PatientIntakeRecord])
async def get_my_intake_history(
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Returns past intake evaluations for the logged-in patient."""
    if not user_id:
        return []

    records = []
    async for rec in db.patient_intakes.find({"patient_id": user_id}).sort("created_at", -1):
        records.append(
            PatientIntakeRecord(
                id=str(rec.get("_id", "")),
                patient_id=rec.get("patient_id"),
                structured_symptoms=rec.get("structured_symptoms", []),
                duration=rec.get("duration"),
                specialty=rec.get("specialty", "General Physician"),
                urgency=rec.get("urgency", "routine"),
                emergency_detected=rec.get("emergency_detected", False),
                created_at=rec.get("created_at", ""),
            )
        )
    return records
