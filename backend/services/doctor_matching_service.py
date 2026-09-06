import datetime
from typing import List, Dict, Any, Optional
from database import db
from models import DoctorMatchItem, SlotItem, ConsultationType
from services.scheduling_service import calculate_available_slots

# Controlled Specialty Mapping to DB Specializations
SPECIALTY_SYNONYM_MAP = {
    "General Physician": ["General Medicine", "General Physician", "Internal Medicine", "Family Medicine", "Physician", "Primary Care", "General Doctor"],
    "Cardiologist": ["Cardiology", "Cardiologist", "Heart", "Cardiac"],
    "Dermatologist": ["Dermatology", "Dermatologist", "Skin", "Derma"],
    "Pediatrician": ["Pediatrics", "Pediatrician", "Child", "Kids", "Infant"],
    "Orthopedic": ["Orthopedics", "Orthopedic", "Orthopaedics", "Bone", "Joint", "Spine"],
    "Neurologist": ["Neurology", "Neurologist", "Brain", "Nerve"],
    "ENT": ["ENT", "Otolaryngology", "Ear Nose Throat", "Ear", "Nose", "Throat"],
    "Dentist": ["Dentistry", "Dentist", "Dental", "Teeth", "Tooth"],
    "Gynecologist": ["Gynecology", "Gynecologist", "Obstetrics & Gynecology", "OB/GYN", "Women's Health"],
}

# Reverse lookup: from database specialization to canonical specialty
CANONICAL_SPECIALTY_MAP = {
    "General Medicine": "General Physician",
    "General Physician": "General Physician",
    "Cardiology": "Cardiologist",
    "Dermatology": "Dermatologist",
    "Pediatrics": "Pediatrician",
    "Orthopedics": "Orthopedic",
    "Neurology": "Neurologist",
    "ENT": "ENT",
    "Dentistry": "Dentist",
    "Gynecology": "Gynecologist",
}


import re


def normalize_specialty(specialty: str) -> str:
    """Normalizes any specialty string to a controlled canonical specialty."""
    if not specialty:
        return "General Physician"
    
    spec_clean = specialty.strip().title()
    if spec_clean in SPECIALTY_SYNONYM_MAP:
        return spec_clean

    spec_lower = specialty.strip().lower()

    # Exact match check
    for canonical, synonyms in SPECIALTY_SYNONYM_MAP.items():
        if canonical.lower() == spec_lower:
            return canonical
        for syn in synonyms:
            if syn.lower() == spec_lower:
                return canonical

    # Word-boundary regex matching to avoid substring collision (e.g. "ent" in "dentistry")
    for canonical, synonyms in SPECIALTY_SYNONYM_MAP.items():
        for syn in synonyms:
            pattern = r"\b" + re.escape(syn.lower()) + r"\b"
            if re.search(pattern, spec_lower):
                return canonical
                
    return "General Physician"


async def match_doctors_for_specialty(
    suggested_specialty: str,
    consultation_type: ConsultationType = ConsultationType.IN_PERSON,
    preferred_date: Optional[str] = None,
    limit: int = 5,
) -> List[DoctorMatchItem]:
    """
    Ranks registered doctors using a multi-factor transparent scoring engine:
      - Specialty Match (40 pts max)
      - Dynamic Next-Slot Availability (25 pts max)
      - Patient Rating (15 pts max)
      - Experience (10 pts max)
      - Consultation Fee (10 pts max)
    """
    canonical_spec = normalize_specialty(suggested_specialty)
    target_synonyms = [s.lower() for s in SPECIALTY_SYNONYM_MAP.get(canonical_spec, [canonical_spec])]

    # Fetch all doctors from database
    doctors_cursor = db.doctors.find({})
    all_doctors = []
    async for d in doctors_cursor:
        d["_id"] = str(d["_id"])
        d["id"] = d["_id"]
        all_doctors.append(d)

    if not all_doctors:
        return []

    today = datetime.date.today()
    start_date = datetime.date.fromisoformat(preferred_date) if preferred_date else today

    ranked_items: List[DoctorMatchItem] = []

    for doc in all_doctors:
        doc_id = doc["_id"]
        doc_name = doc.get("name", "Specialist")
        doc_spec = doc.get("specialization", "General Medicine")
        experience = int(doc.get("experience", 5))
        fee = int(doc.get("fee", 500))
        rating = float(doc.get("rating", 4.8))

        match_score = 0
        match_reasons = []

        # 1. Specialty Score (Max 40)
        if doc_spec.lower() in target_synonyms:
            match_score += 40
            match_reasons.append(f"Direct specialty match: {doc_spec}")
        elif doc_spec.lower() in ["general medicine", "general physician", "internal medicine"]:
            match_score += 20
            match_reasons.append("Primary care & general medical evaluation")
        else:
            match_score += 5
            match_reasons.append(f"Alternative specialist: {doc_spec}")

        # 2. Dynamic Slot Availability Scan over next 7 days (Max 25)
        earliest_date_str = None
        next_slots: List[SlotItem] = []
        days_ahead = 0

        for offset in range(7):
            query_date = start_date + datetime.timedelta(days=offset)
            date_iso = query_date.isoformat()
            
            try:
                avail_res = await calculate_available_slots(
                    doctor_id=doc_id,
                    date_str=date_iso,
                    appointment_type=consultation_type,
                )
                if avail_res.available_slots:
                    earliest_date_str = date_iso
                    days_ahead = offset
                    next_slots = avail_res.available_slots[:3]  # top 3 next slots
                    break
            except Exception:
                continue

        if earliest_date_str:
            if days_ahead == 0:
                match_score += 25
                match_reasons.append("Available today for immediate appointment")
            elif days_ahead <= 2:
                match_score += 18
                match_reasons.append(f"Available within {days_ahead + 1} days ({earliest_date_str})")
            else:
                match_score += 10
                match_reasons.append(f"Next available date: {earliest_date_str}")
        else:
            match_score += 0
            match_reasons.append("No open slots found in the next 7 days")

        # 3. Rating Score (Max 15)
        rating_pts = int(round((rating / 5.0) * 15))
        match_score += rating_pts
        match_reasons.append(f"{rating}★ verified patient satisfaction")

        # 4. Clinical Experience Score (Max 10)
        exp_pts = min(10, max(2, experience))
        match_score += exp_pts
        match_reasons.append(f"{experience} years clinical experience")

        # 5. Consultation Fee Score (Max 10)
        fee_pts = max(2, min(10, 10 - (fee // 100)))
        match_score += fee_pts

        # Cap total score at 100
        match_score = min(100, match_score)

        ranked_items.append(
            DoctorMatchItem(
                doctor_id=doc_id,
                doctor_name=f"Dr. {doc_name}" if not doc_name.startswith("Dr.") else doc_name,
                specialization=doc_spec,
                experience=experience,
                fee=fee,
                rating=rating,
                match_score=match_score,
                match_reasons=match_reasons,
                available_date=earliest_date_str,
                next_available_slots=next_slots,
            )
        )

    # Sort descending by match_score
    ranked_items.sort(key=lambda item: item.match_score, reverse=True)
    return ranked_items[:limit]
