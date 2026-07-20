from fastapi import APIRouter, Depends, HTTPException
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError

from config import GEMINI_API_KEY
from models import SymptomCheckRequest
from dependencies import require_premium

router = APIRouter(tags=["premium"])

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "You are a cautious medical triage assistant inside a healthcare booking app. "
    "Given a list of symptoms, suggest 2-4 possible general causes in plain language, "
    "note any red-flag symptoms that need urgent in-person care, and always end by "
    "recommending the user book an appointment with a relevant specialist rather than "
    "self-diagnose. Never give a definitive diagnosis or prescribe medication."
)

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_PROMPT,
)


@router.post("/premium/symptom-checker")
async def symptom_checker(data: SymptomCheckRequest, user: dict = Depends(require_premium)):
    try:
        response = model.generate_content(
            data.symptoms,
            generation_config={"max_output_tokens": 400},
        )
    except GoogleAPIError:
        raise HTTPException(502, "Symptom checker is temporarily unavailable")

    if not response.text:
        raise HTTPException(502, "Symptom checker returned an empty response")

    return {"result": response.text}
