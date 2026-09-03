from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_indexes, db
from redis_client import get_redis, close_redis, is_redis_connected
from routers import auth_routes, doctors, appointments, slots, payment, symptom_checker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_indexes()
    await get_redis()
    yield
    # Shutdown
    await close_redis()


app = FastAPI(
    title="MediBook API - Intelligent Healthcare Scheduling Platform",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Modular Routers
app.include_router(auth_routes.router)
app.include_router(doctors.router)
app.include_router(slots.router)
app.include_router(appointments.router)
app.include_router(payment.router)
app.include_router(symptom_checker.router)


@app.get("/")
def home():
    return {
        "app": "MediBook Healthcare API",
        "version": "2.0.0",
        "status": "online"
    }


@app.get("/health")
async def health_check():
    """Service health check verifying MongoDB and Redis connection status."""
    mongo_ok = False
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False

    redis_ok = await is_redis_connected()

    overall_status = "healthy" if (mongo_ok) else "degraded"
    return {
        "status": overall_status,
        "database": "connected" if mongo_ok else "disconnected",
        "cache_and_locks": "redis" if redis_ok else "in-memory-fallback",
    }
