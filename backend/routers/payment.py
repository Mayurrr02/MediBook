import datetime
import hashlib
import hmac

import razorpay
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, PREMIUM_AMOUNT_PAISE
from database import db
from models import PaymentVerify
from dependencies import get_current_user

router = APIRouter(prefix="/payment", tags=["payment"])

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


@router.post("/create-order")
async def create_order(user: dict = Depends(get_current_user)):
    order = client.order.create({
        "amount": PREMIUM_AMOUNT_PAISE,
        "currency": "INR",
        "payment_capture": 1,
        "notes": {"user_id": user["_id"]},
    })
    return {
        "order_id": order["id"],
        "amount": PREMIUM_AMOUNT_PAISE,
        "currency": "INR",
        "key": RAZORPAY_KEY_ID,
    }


async def _mark_premium(user_id: str, payment_id: str):
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "is_premium": True,
            "premium_since": datetime.datetime.utcnow(),
            "razorpay_payment_id": payment_id,
        }},
    )


@router.post("/verify")
async def verify_payment(data: PaymentVerify, user: dict = Depends(get_current_user)):
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": data.razorpay_order_id,
            "razorpay_payment_id": data.razorpay_payment_id,
            "razorpay_signature": data.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(400, "Payment verification failed")

    await _mark_premium(user["_id"], data.razorpay_payment_id)
    return {"status": "premium unlocked"}


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """Backup path: fires even if the user closes the tab before the
    frontend calls /verify. Configure this URL in the Razorpay dashboard
    with the 'payment.captured' event enabled."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid webhook signature")

    payload = await request.json()
    if payload.get("event") == "payment.captured":
        payment_entity = payload["payload"]["payment"]["entity"]
        user_id = payment_entity.get("notes", {}).get("user_id")
        if user_id:
            await _mark_premium(user_id, payment_entity["id"])

    return {"status": "ok"}
