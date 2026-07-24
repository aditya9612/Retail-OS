import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login(unique_slug):
    email = f"owner-{unique_slug}@testcorp.com"
    register_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Test Corp",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Test Owner",
            "password": "testpass123",
        },
    )
    assert register_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
