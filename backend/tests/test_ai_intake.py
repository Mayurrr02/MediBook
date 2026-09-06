import pytest
import datetime
from httpx import AsyncClient, ASGITransport
from main import app
from database import db
from models import ConsultationType, AIIntakeRequest, UrgencyLevel
from services.emergency_detector import scan_for_emergencies
from services.doctor_matching_service import normalize_specialty, match_doctors_for_specialty
from services.ai_intake_service import process_patient_intake, _heuristic_intake_fallback, check_ai_rate_limit


@pytest.mark.asyncio
async def test_deterministic_emergency_detection():
    # Cardiac emergency trigger
    cardiac_res = scan_for_emergencies("I have crushing chest pain and severe shortness of breath")
    assert cardiac_res["is_emergency"] is True
    assert len(cardiac_res["matched_triggers"]) > 0
    assert "112 / 911" in cardiac_res["advice"]

    # Stroke / neurological emergency trigger
    stroke_res = scan_for_emergencies("My grandmother has facial droop and sudden slurred speech")
    assert stroke_res["is_emergency"] is True
    assert "stroke" in str(stroke_res["matched_triggers"]).lower() or "neurological" in str(stroke_res["matched_triggers"]).lower()

    # Routine non-emergency query
    routine_res = scan_for_emergencies("I have had a mild dry cough and slight runny nose since yesterday")
    assert routine_res["is_emergency"] is False
    assert routine_res["advice"] is None


@pytest.mark.asyncio
async def test_specialty_normalization_and_mapping():
    assert normalize_specialty("cardiology") == "Cardiologist"
    assert normalize_specialty("Cardiologist") == "Cardiologist"
    assert normalize_specialty("skin specialist") == "Dermatologist"
    assert normalize_specialty("Dermatology") == "Dermatologist"
    assert normalize_specialty("Pediatrics") == "Pediatrician"
    assert normalize_specialty("Ear Nose Throat") == "ENT"
    assert normalize_specialty("Orthopedic Surgeon") == "Orthopedic"
    assert normalize_specialty("Dentistry") == "Dentist"
    # Fallback on unsupported / unknown
    assert normalize_specialty("Cosmic Healer") == "General Physician"
    assert normalize_specialty("") == "General Physician"


@pytest.mark.asyncio
async def test_heuristic_intake_fallback_parsing():
    res = _heuristic_intake_fallback("I have had a bad cough, fever, and fatigue for 5 days")
    assert "cough" in res.symptoms
    assert "fever" in res.symptoms
    assert res.duration == "5 days"
    assert res.suggested_specialty == "General Physician"
    assert res.urgency == UrgencyLevel.ROUTINE
    assert res.emergency_detected is False


@pytest.mark.asyncio
async def test_doctor_matching_engine():
    await db.doctors.delete_many({})
    await db.doctor_availabilities.delete_many({})

    # Insert 2 test doctors
    doc_cardio = await db.doctors.insert_one({
        "name": "Dr. Sarah Heart",
        "specialization": "Cardiology",
        "experience": 15,
        "fee": 600,
        "rating": 4.9,
    })
    doc_general = await db.doctors.insert_one({
        "name": "Dr. John General",
        "specialization": "General Medicine",
        "experience": 8,
        "fee": 400,
        "rating": 4.7,
    })

    # Add availability schedule for Cardio doctor
    await db.doctor_availabilities.insert_one({
        "doctor_id": str(doc_cardio.inserted_id),
        "working_days": [0, 1, 2, 3, 4, 5, 6],
        "shifts": [{"start_time": "09:00", "end_time": "17:00"}],
        "breaks": [],
        "duration_minutes": 30,
        "buffer_minutes": 10,
        "consultation_types": ["IN_PERSON", "VIDEO"],
    })

    matches = await match_doctors_for_specialty("Cardiologist", limit=5)
    assert len(matches) >= 2
    top_match = matches[0]
    assert top_match.doctor_id == str(doc_cardio.inserted_id)
    assert top_match.specialization == "Cardiology"
    assert top_match.match_score >= 60
    assert any("Direct specialty match" in r for r in top_match.match_reasons)


@pytest.mark.asyncio
async def test_end_to_end_patient_intake_pipeline():
    # End-to-end intake request with knee symptoms
    req = AIIntakeRequest(
        message="I twisted my knee while playing football 2 days ago and have swelling and pain",
        consultation_type=ConsultationType.IN_PERSON,
    )
    res = await process_patient_intake(req, client_ip="192.168.1.100")
    
    assert res.intake.suggested_specialty in ["Orthopedic", "General Physician"]
    assert len(res.intake.symptoms) > 0
    assert res.intake.duration == "2 days"
    assert res.disclaimer is not None
    assert "does NOT constitute a medical diagnosis" in res.disclaimer


@pytest.mark.asyncio
async def test_emergency_intake_pipeline_override():
    # Request containing life-threatening symptoms
    req = AIIntakeRequest(
        message="My father has sudden crushing chest pain and is sweating and cannot breathe",
        consultation_type=ConsultationType.IN_PERSON,
    )
    res = await process_patient_intake(req, client_ip="192.168.1.101")
    
    assert res.intake.emergency_detected is True
    assert res.intake.urgency == UrgencyLevel.EMERGENCY
    assert res.emergency_alert is not None
    assert "112 / 911" in res.emergency_alert


@pytest.mark.asyncio
async def test_ai_intake_rest_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Get supported specialties
        spec_res = await ac.get("/api/v1/ai/specialties")
        assert spec_res.status_code == 200
        specialties = spec_res.json()
        assert "General Physician" in specialties
        assert "Cardiologist" in specialties

        # 2. Submit AI intake
        intake_res = await ac.post(
            "/api/v1/ai/intake",
            json={"message": "I have itchy red rash and hives on my hands for 3 days"},
        )
        assert intake_res.status_code == 200
        data = intake_res.json()
        assert "intake" in data
        assert "matched_doctors" in data
        assert data["intake"]["suggested_specialty"] in ["Dermatologist", "General Physician"]


@pytest.mark.asyncio
async def test_ai_rate_limiting():
    client_test_id = "test_rate_limit_client_ip"
    # Fire up to limit (12)
    for _ in range(12):
        allowed = await check_ai_rate_limit(client_test_id, limit=12, window_seconds=60)
        assert allowed is True
    
    # 13th should be blocked
    blocked = await check_ai_rate_limit(client_test_id, limit=12, window_seconds=60)
    assert blocked is False


@pytest.mark.asyncio
async def test_patient_intake_history_persistence():
    req = AIIntakeRequest(
        message="Mild sore throat and sneezing since morning",
        patient_id="60c72b2f9b1d8b2bad000777",
        consultation_type=ConsultationType.IN_PERSON,
    )
    res = await process_patient_intake(req, client_ip="192.168.1.102")
    assert res.intake.suggested_specialty in ["ENT", "General Physician"]
    
    saved_doc = await db.patient_intakes.find_one({"patient_id": "60c72b2f9b1d8b2bad000777"})
    assert saved_doc is not None
    assert saved_doc["specialty"] == res.intake.suggested_specialty
    assert saved_doc["emergency_detected"] is False
