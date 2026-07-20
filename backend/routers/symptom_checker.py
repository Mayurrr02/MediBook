from fastapi import APIRouter, Depends, HTTPException
from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import GEMINI_API_KEY
from models import SymptomCheckRequest
from dependencies import require_premium

router = APIRouter(tags=["premium"])

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "You are a cautious medical triage assistant inside a healthcare booking app. "
    "Given a list of symptoms, provide a thorough response: suggest 3-5 possible "
    "general causes with a brief explanation of each, list any red-flag symptoms "
    "that need urgent in-person care, suggest general self-care steps if appropriate, "
    "and always end by recommending the user book an appointment with a relevant "
    "specialist rather than self-diagnose. Never give a definitive diagnosis or "
    "prescribe medication. Aim for a detailed, well-organized response using clear "
    "sections rather than a short summary."
)


@router.post("/premium/symptom-checker")
async def symptom_checker(data: SymptomCheckRequest, user: dict = Depends(require_premium)):
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=data.symptoms,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1500,
            ),
        )
    except APIError:
        raise HTTPException(502, "Symptom checker is temporarily unavailable")

    if not response.text:
        raise HTTPException(502, "Symptom checker returned an empty response")

    truncated = False
    try:
        truncated = response.candidates[0].finish_reason == "MAX_TOKENS"
    except (IndexError, AttributeError):
        pass

    return {"result": response.text, "truncated": truncated}