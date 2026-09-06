import json
import re
import datetime
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from pydantic import ValidationError

from config import GEMINI_API_KEY
from database import db
from redis_client import get_redis
from models import (
    AIIntakeRequest,
    AIStructuredIntake,
    AIIntakeResponse,
    UrgencyLevel,
    SupportedSpecialty,
)
from services.emergency_detector import scan_for_emergencies
from services.doctor_matching_service import match_doctors_for_specialty, normalize_specialty

# Supported Specialties List for Prompt Enforcement
ALLOWED_SPECIALTIES = [s.value for s in SupportedSpecialty]

AI_SYSTEM_INSTRUCTION = f"""
You are the MediBook AI Triage & Intake Assistant.
Your primary role is to extract structured patient symptom information and suggest an appropriate medical specialty from a predefined list.

STRICT MEDICAL SAFETY RULES:
1. NEVER diagnose illnesses or diseases (do NOT say "You have pneumonia" or "This is COVID-19").
2. NEVER prescribe or suggest prescription medications.
3. Formulate all advice as scheduling and consultation guidance (e.g. "A consultation with a General Physician may be appropriate to evaluate your symptoms.").
4. Map your suggestion strictly to one of the following allowed specialties:
{json.dumps(ALLOWED_SPECIALTIES)}

Output MUST be a single valid JSON object with EXACTLY the following keys:
{{
  "symptoms": ["list", "of", "extracted", "symptoms"],
  "duration": "extracted duration (e.g. '5 days', 'since morning', 'unknown')",
  "severity": "mild | moderate | severe | unknown",
  "suggested_specialty": "One specialty strictly from the allowed list",
  "urgency": "routine | urgent | emergency",
  "reasoning": "A concise, non-diagnostic 1-2 sentence explanation of why this specialty is suitable."
}}
"""

# In-Memory Rate Limiting Fallback Store
_in_memory_rate_limits: Dict[str, List[float]] = {}


async def check_ai_rate_limit(client_id: str, limit: int = 10, window_seconds: int = 60) -> bool:
    """
    Enforces rate limits on AI intake requests (default 10 requests per minute).
    Uses Redis when online, with fallback to in-memory timestamp tracking.
    """
    now = datetime.datetime.utcnow().timestamp()
    redis = await get_redis()
    
    if redis:
        try:
            key = f"ai_intake_ratelimit:{client_id}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
            if count > limit:
                return False
            return True
        except Exception:
            pass

    # In-memory fallback
    timestamps = _in_memory_rate_limits.get(client_id, [])
    # Filter out timestamps outside window
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= limit:
        return False
    timestamps.append(now)
    _in_memory_rate_limits[client_id] = timestamps
    return True


def _heuristic_intake_fallback(message: str) -> AIStructuredIntake:
    """
    Resilient rule-based parser that executes when external AI provider is unavailable,
    ensuring MediBook intake and scheduling functions without disruption.
    """
    msg_lower = message.lower()
    extracted_symptoms = []

    # Symptom keyword dictionary
    keyword_map = [
        ("chest pain", "chest pain"),
        ("cough", "cough"),
        ("fever", "fever"),
        ("headache", "headache"),
        ("migraine", "migraine"),
        ("rash", "skin rash"),
        ("itch", "skin itching"),
        ("acne", "acne"),
        ("knee pain", "knee pain"),
        ("joint pain", "joint pain"),
        ("back pain", "back pain"),
        ("sore throat", "sore throat"),
        ("ear pain", "earache"),
        ("toothache", "toothache"),
        ("stomach pain", "abdominal discomfort"),
        ("nausea", "nausea"),
        ("vomit", "vomiting"),
        ("dizz", "dizziness"),
        ("shortness of breath", "shortness of breath"),
        ("fatigue", "fatigue"),
    ]

    for kw, sym_name in keyword_map:
        if kw in msg_lower:
            extracted_symptoms.append(sym_name)

    if not extracted_symptoms:
        extracted_symptoms = ["General health concern"]

    # Duration extraction via regex
    duration = "unknown"
    dur_match = re.search(r"\b(\d+\s*(?:days?|weeks?|months?|years?|hours?|hrs?))\b", msg_lower)
    if dur_match:
        duration = dur_match.group(1).strip()
    else:
        dur_match_alt = re.search(r"\b(since\s+\w+|for\s+\d+\s*\w+)\b", msg_lower)
        if dur_match_alt:
            duration = dur_match_alt.group(1).strip()

    # Specialty mapping heuristics
    suggested_specialty = "General Physician"
    if any(k in msg_lower for k in ["heart", "chest", "palpitation", "cardio"]):
        suggested_specialty = "Cardiologist"
    elif any(k in msg_lower for k in ["skin", "rash", "acne", "itch", "eczema", "dermat"]):
        suggested_specialty = "Dermatologist"
    elif any(k in msg_lower for k in ["knee", "bone", "joint", "fracture", "sprain", "ortho", "spine"]):
        suggested_specialty = "Orthopedic"
    elif any(k in msg_lower for k in ["ear", "nose", "throat", "sinus", "tonsil", "hearing"]):
        suggested_specialty = "ENT"
    elif any(k in msg_lower for k in ["headache", "migraine", "numbness", "nerve", "seizure", "neuro"]):
        suggested_specialty = "Neurologist"
    elif any(k in msg_lower for k in ["tooth", "teeth", "gum", "dent"]):
        suggested_specialty = "Dentist"
    elif any(k in msg_lower for k in ["infant", "toddler", "pediatric", "child", "baby"]):
        suggested_specialty = "Pediatrician"
    elif any(k in msg_lower for k in ["period", "menstrual", "pregnancy", "gynec"]):
        suggested_specialty = "Gynecologist"

    # Severity heuristics
    severity = "moderate" if any(w in msg_lower for w in ["severe", "unbearable", "high", "intense"]) else "mild"

    return AIStructuredIntake(
        symptoms=extracted_symptoms,
        duration=duration,
        severity=severity,
        suggested_specialty=suggested_specialty,
        urgency=UrgencyLevel.ROUTINE,
        reasoning=f"Based on reported symptoms, consultation with a {suggested_specialty} is recommended for evaluation.",
        emergency_detected=False,
    )


async def process_patient_intake(
    request: AIIntakeRequest,
    client_ip: str = "127.0.0.1",
) -> AIIntakeResponse:
    """
    Coordinates end-to-end AI intake:
      1. Rate Limit Enforcement
      2. Deterministic Emergency Scanner
      3. Structured LLM / Fallback Inference
      4. Controlled Specialty Normalization
      5. Doctor Matching & Slot Recommendations
      6. Privacy-Preserving Persistence
    """
    # 1. Rate Limit Check
    rate_limit_id = request.patient_id or client_ip
    is_allowed = await check_ai_rate_limit(rate_limit_id, limit=12, window_seconds=60)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail="AI Assistant request limit reached. Please wait a minute before submitting again."
        )

    # 2. Deterministic Emergency Scan
    emergency_info = scan_for_emergencies(request.message)
    structured_intake: Optional[AIStructuredIntake] = None

    # 3. LLM Structured Extraction (Google GenAI Gemini)
    if GEMINI_API_KEY:
        try:
            from google import genai
            import importlib
            types = importlib.import_module("google.genai.types")
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=request.message,
                config=types.GenerateContentConfig(
                    system_instruction=AI_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    max_output_tokens=600,
                ),
            )

            if response and response.text:
                parsed_json = json.loads(response.text)
                
                # Normalize urgency string
                urgency_raw = str(parsed_json.get("urgency", "routine")).lower()
                urgency_enum = UrgencyLevel.ROUTINE
                if urgency_raw == "emergency":
                    urgency_enum = UrgencyLevel.EMERGENCY
                elif urgency_raw == "urgent":
                    urgency_enum = UrgencyLevel.URGENT

                structured_intake = AIStructuredIntake(
                    symptoms=parsed_json.get("symptoms", []),
                    duration=parsed_json.get("duration", "unknown"),
                    severity=parsed_json.get("severity", "unknown"),
                    suggested_specialty=normalize_specialty(parsed_json.get("suggested_specialty", "General Physician")),
                    urgency=urgency_enum,
                    reasoning=parsed_json.get("reasoning"),
                    emergency_detected=False,
                )
        except Exception as e:
            # On LLM error, log and drop through to heuristic fallback
            print(f"[AI Intake Warning] LLM parsing failed, falling back to heuristic: {e}")
            structured_intake = None

    # Fallback to Heuristic Engine if LLM was skipped or failed
    if not structured_intake:
        structured_intake = _heuristic_intake_fallback(request.message)

    # 4. Enforce Deterministic Safety Override
    if emergency_info["is_emergency"]:
        structured_intake.emergency_detected = True
        structured_intake.urgency = UrgencyLevel.EMERGENCY
        structured_intake.emergency_advice = emergency_info["advice"]

    # Normalize suggested specialty strictly
    structured_intake.suggested_specialty = normalize_specialty(structured_intake.suggested_specialty)

    # 5. Doctor Matching & Available Slots
    matched_doctors = await match_doctors_for_specialty(
        suggested_specialty=structured_intake.suggested_specialty,
        consultation_type=request.consultation_type,
        preferred_date=request.preferred_date,
        limit=5,
    )

    # 6. Minimal Privacy-Compliant Intake Record Storage
    try:
        intake_doc = {
            "patient_id": request.patient_id or "anonymous",
            "structured_symptoms": structured_intake.symptoms,
            "duration": structured_intake.duration,
            "specialty": structured_intake.suggested_specialty,
            "urgency": structured_intake.urgency.value,
            "emergency_detected": structured_intake.emergency_detected,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        await db.patient_intakes.insert_one(intake_doc)
    except Exception as e:
        print(f"[Warning] Failed to persist patient intake record: {e}")

    emergency_alert = emergency_info["advice"] if emergency_info["is_emergency"] else None

    return AIIntakeResponse(
        intake=structured_intake,
        recommended_specialty=structured_intake.suggested_specialty,
        matched_doctors=matched_doctors,
        emergency_alert=emergency_alert,
    )
