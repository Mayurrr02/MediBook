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
        assert "cache_and_locks" in health_data


@pytest.mark.asyncio
async def test_get_doctor_slots_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        doc_id = "60c72b2f9b1d8b2bad000001"
        res = await ac.get(f"/doctors/{doc_id}/slots?date=2026-10-15")
        assert res.status_code == 200
        data = res.json()
        assert data["doctor_id"] == doc_id
        assert data["date"] == "2026-10-15"
        assert "slots" in data
        assert len(data["slots"]) > 0


@pytest.mark.asyncio
async def test_slot_lock_and_unlock_api_flow():
    headers = {"Authorization": "Bearer mock_token_header"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        doc_id = "60c72b2f9b1d8b2bad000001"
        date = "2026-10-15"
        time_slot = "11:30 AM"

        # 1. Lock slot
        lock_res = await ac.post(
            "/slots/lock",
            json={"doctor_id": doc_id, "date": date, "time": time_slot, "ttl_seconds": 60},
            headers=headers
        )
        assert lock_res.status_code == 200
        lock_data = lock_res.json()
        assert lock_data["success"] is True
        lock_token = lock_data["lock_token"]
        assert lock_token is not None

        # 2. Unlock slot
        unlock_res = await ac.post(
            "/slots/unlock",
            json={"doctor_id": doc_id, "date": date, "time": time_slot, "lock_token": lock_token},
            headers=headers
        )
        assert unlock_res.status_code == 200
        assert unlock_res.json()["status"] == "unlocked"
