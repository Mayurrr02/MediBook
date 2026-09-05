import pytest
from httpx import AsyncClient, ASGITransport
from main import app
from dependencies import get_current_user

# Mock authenticated user for API testing
MOCK_USER = {
    "_id": "60c72b2f9b1d8b2bad000002",
    "name": "Test Patient",
    "email": "test@example.com",
    "role": "PATIENT",
    "is_admin": False,
    "is_premium": False,
}


@pytest.fixture(autouse=True)
def override_user_dependency():
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_home_and_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["app"] == "MediBook Healthcare API"

        health_res = await ac.get("/health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert "status" in health_data


@pytest.mark.asyncio
async def test_get_available_slots_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        doc_id = "60c72b2f9b1d8b2bad000001"
        # Test Monday slot generation
        res = await ac.get(f"/api/v1/appointments/available-slots?doctor_id={doc_id}&date=2026-10-12&appointment_type=IN_PERSON")
        assert res.status_code == 200
        data = res.json()
        assert data["doctor_id"] == doc_id
        assert data["date"] == "2026-10-12"
        assert "available_slots" in data
        assert "booked_slots" in data
        assert "unavailable_periods" in data
        assert data["duration_minutes"] == 30
        assert data["buffer_minutes"] == 10


@pytest.mark.asyncio
async def test_get_doctor_availability_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        doc_id = "60c72b2f9b1d8b2bad000001"
        res = await ac.get(f"/api/v1/doctors/{doc_id}/availability")
        assert res.status_code == 200
        data = res.json()
        assert "working_days" in data
        assert "shifts" in data
        assert "breaks" in data
