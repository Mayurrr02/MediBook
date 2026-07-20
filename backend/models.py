from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)


class Login(BaseModel):
    email: EmailStr
    password: str


class Doctor(BaseModel):
    name: str
    specialization: str
    experience: int
    fee: int


class Appointment(BaseModel):
    doctor_id: str
    date: str  # YYYY-MM-DD
    time: str  # e.g. "10:00 AM"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str = "INR"
    key: str


class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class SymptomCheckRequest(BaseModel):
    symptoms: str = Field(min_length=3, max_length=1000)
