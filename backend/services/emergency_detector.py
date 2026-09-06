import re
from typing import Dict, Any, List

# Predefined deterministic high-risk indicators
RED_FLAG_PATTERNS = [
    # Cardiac & Chest Pain
    (r"\b(chest pain|crushing (chest|pain)|pressure in (my )?chest|pain (radiating|spreading) to (arm|jaw|back|neck)|heart attack)\b", "Severe chest pressure or potential cardiac event"),
    # Respiratory Distress
    (r"\b(can'?t breathe|cannot breathe|struggling to breathe|severe shortness of breath|choking|stridor|gasping for (air|breath)|blue (lips|fingers)|cyanosis)\b", "Acute respiratory distress"),
    # Neurological & Stroke (FAST criteria)
    (r"\b(face drooping|facial droop|slurred speech|speech difficulty|sudden paralysis|loss of vision|worst headache of (my )?life|thunderclap headache|sudden weakness (in|on) one side)\b", "Possible acute neurological or stroke event"),
    # Consciousness & Trauma
    (r"\b(lost consciousness|passed out|fainted and (not waking|unresponsive)|unconscious|unresponsive|severe head (injury|trauma)|active seizure)\b", "Altered consciousness or active seizure"),
    # Hemorrhage & Vascular
    (r"\b(coughing (up )?blood|vomiting blood|uncontrolled bleeding|severe bleeding|gushing blood)\b", "Severe acute hemorrhage"),
    # Anaphylaxis
    (r"\b(throat (closing|swelling)|swollen (tongue|lips) and (can'?t|cannot) breathe|anaphylax(is|ic))\b", "Severe allergic reaction (anaphylaxis)"),
    # Poisoning & Severe Intoxication
    (r"\b(swallowed (poison|bleach|chemical)|drug overdose|accidental overdose)\b", "Acute poisoning or overdose"),
]

COMPILED_PATTERNS = [(re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in RED_FLAG_PATTERNS]

EMERGENCY_ADVICE_TEMPLATE = (
    "EMERGENCY WARNING: Potential high-risk indicators detected ({triggers}). "
    "Please seek IMMEDIATE emergency medical assistance by calling 112 / 911 / 102 "
    "or proceed to the nearest Emergency Department. "
    "Do not delay care by waiting for a scheduled routine consultation."
)


def scan_for_emergencies(text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based safety scanner to detect acute, life-threatening symptoms
    independently of LLM inference.
    """
    if not text or not isinstance(text, str):
        return {"is_emergency": False, "matched_triggers": [], "advice": None}

    matched_triggers = []
    for regex, description in COMPILED_PATTERNS:
        if regex.search(text):
            matched_triggers.append(description)

    is_emergency = len(matched_triggers) > 0
    advice = None
    if is_emergency:
        advice = EMERGENCY_ADVICE_TEMPLATE.format(triggers=", ".join(matched_triggers))

    return {
        "is_emergency": is_emergency,
        "matched_triggers": matched_triggers,
        "advice": advice,
    }
