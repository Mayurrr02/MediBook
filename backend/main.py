from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_indexes
from routers import auth_routes, doctors, appointments, payment, symptom_checker

app = FastAPI(title="MediBook API")
origins = [
    "https://medibook-1-moc8.onrender.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(payment.router)
app.include_router(symptom_checker.router)


@app.on_event("startup")
async def on_startup():
    await init_indexes()


@app.get("/")
def home():
    return {"message": "MediBook API running"}
