from pydantic import BaseModel

# USER MODEL
class User(BaseModel):
    name: str
    email: str
    password: str

# LOGIN MODEL
class Login(BaseModel):
    email: str
    password: str

# DOCTOR MODEL
class Doctor(BaseModel):
    name: str
    specialization: str
    experience: int
    fee: int

# APPOINTMENT MODEL
class Appointment(BaseModel):
    doctor_id: str
    date: str