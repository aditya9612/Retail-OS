import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_validation_error_formatting_missing_required_fields(unique_slug):
    """
    Test that sending empty or missing required fields in any API endpoint
    returns HTTP 422 with a structured, human-readable 'message' and 'detail'
    and NEVER a 500 Internal Server Error.
    """
    # Attempt to register without required fields
    resp = client.post("/api/v1/auth/register", json={})
    assert resp.status_code == 422
    data = resp.json()
    assert data["success"] is False
    assert "message" in data
    assert "Validation failed" in data["message"]
    assert "detail" in data
    assert isinstance(data["detail"], list)
    assert len(data["detail"]) > 0
    assert "errors" in data
    assert len(data["errors"]) > 0
    # Field names should be clearly identified
    error_fields = [e["field"] for e in data["errors"]]
    assert any("email" in f or "store_name" in f for f in error_fields)


def test_validation_error_formatting_type_mismatch(unique_slug):
    """
    Test that sending mismatched types (e.g. string for integer)
    returns HTTP 422 with a clear explanation of what was mismatched.
    """
    # Register and login owner
    owner_email = f"owner-valtype-{unique_slug}@retailstore.com"
    owner_phone = f"97{abs(hash(unique_slug + 'valtype')) % 100000000:08d}"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"ValType Store {unique_slug}",
            "domain": f"vt-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": owner_phone,
        },
    )
    assert reg_res.status_code == 200

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Query param type mismatch: page="not_a_number"
    resp = client.get("/api/v1/users?page=invalid_number", headers=headers)
    assert resp.status_code == 422
    data = resp.json()
    assert data["success"] is False
    assert "page" in str(data["message"]) or "page" in str(data["detail"])

    # Path param type mismatch: user_id="abc"
    resp_path = client.get("/api/v1/users/not_an_id", headers=headers)
    assert resp_path.status_code == 422
    data_path = resp_path.json()
    assert data_path["success"] is False
    assert "user_id" in str(data_path["message"]) or "user_id" in str(data_path["detail"])


def test_create_user_invalid_phone_format_returns_proper_message(unique_slug):
    """
    Test that phone format mismatch returns a clear 422 message indicating
    the 10-digit Indian phone requirement, NEVER a 500 error.
    """
    owner_email = f"owner-phoneval-{unique_slug}@retailstore.com"
    owner_phone = f"97{abs(hash(unique_slug + 'phoneval')) % 100000000:08d}"
    client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"PhoneVal Store {unique_slug}",
            "domain": f"pv-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": owner_phone,
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Post with invalid phone (special character / wrong format)
    resp = client.post(
        "/api/v1/users",
        headers=headers,
        data={
            "email": f"badphone-{unique_slug}@store.com",
            "full_name": "Invalid Phone User",
            "password": "Password@123!",
            "role": "staff",
            "phone": "989898989*8",
        },
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["success"] is False
    assert "Invalid Indian mobile number" in str(data)
    assert "phone" in str(data["message"]).lower() or "phone" in str(data["detail"]).lower()


def test_foreign_key_or_nonexistent_reference_returns_clear_error(unique_slug):
    """
    Test that referencing a non-existent parent resource (like store_id=999999)
    returns an informative 400 or 404 error, NEVER an unhandled 500 database crash.
    """
    owner_email = f"owner-fk-{unique_slug}@retailstore.com"
    owner_phone = f"97{abs(hash(unique_slug + 'fk')) % 100000000:08d}"
    client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"FK Store {unique_slug}",
            "domain": f"fk-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": owner_phone,
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Reference non-existent store_id 999999
    resp = client.post(
        "/api/v1/users",
        headers=headers,
        data={
            "email": f"userfk-{unique_slug}@store.com",
            "full_name": "FK User",
            "password": "Password@123!",
            "role": "staff",
            "phone": f"96{abs(hash(unique_slug + 'userfk')) % 100000000:08d}",
            "store_id": 999999,
        },
    )
    # Must NOT be 500!
    assert resp.status_code in [400, 404]
    data = resp.json()
    assert data["success"] is False
    assert "store" in str(data).lower() or "not found" in str(data).lower() or "exist" in str(data).lower()

