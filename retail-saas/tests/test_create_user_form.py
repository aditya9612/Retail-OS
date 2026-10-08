import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
    }


def test_create_user_with_form_data_and_kyc_files():
    tenant = create_tenant_and_admin("userform")
    headers = tenant["headers"]

    user_email = f"emp-{uuid.uuid4().hex[:6]}@example.com"

    # Dummy files
    pancard_file = ("pancard.png", io.BytesIO(b"dummy pan card image bytes"), "image/png")
    addhar_file = ("aadhaar.pdf", io.BytesIO(b"%PDF dummy aadhaar card bytes"), "application/pdf")
    photo_file = ("avatar.jpg", io.BytesIO(b"dummy profile photo bytes"), "image/jpeg")

    form_data = {
        "email": user_email,
        "full_name": "Rohan Deshmukh",
        "password": "Password123!",
        "role": "staff",
        "phone": "9876543210",
        "pan_number": "ABCDE1234F",
        "addhar_number": "9876 5432 1012",
    }

    files = {
        "pancard": pancard_file,
        "addhar_card": addhar_file,
        "profile_photo": photo_file,
    }

    # POST /api/v1/users with multipart/form-data
    resp = client.post(
        "/api/v1/users",
        data=form_data,
        files=files,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()

    assert user["email"] == user_email
    assert user["full_name"] == "Rohan Deshmukh"
    assert user["phone"] == "9876543210"
    assert user["role"]["name"] == "staff"
    assert user["pan_number"] == "ABCDE1234F"
    assert user["addhar_number"] == "987654321012"
    assert user["pancard"] is not None and user["pancard"].startswith("/uploads/users/pancard_")
    assert user["addhar_card"] is not None and user["addhar_card"].startswith("/uploads/users/addhar_card_")
    assert user["profile_photo"] is not None and user["profile_photo"].startswith("/uploads/users/profile_photo_")

    # Verify retrieval GET /api/v1/users/{id}
    user_id = user["id"]
    get_resp = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert get_resp.status_code == 200
    fetched_user = get_resp.json()
    assert fetched_user["pan_number"] == "ABCDE1234F"
    assert fetched_user["addhar_number"] == "987654321012"
    assert fetched_user["pancard"] == user["pancard"]
    assert fetched_user["addhar_card"] == user["addhar_card"]
    assert fetched_user["profile_photo"] == user["profile_photo"]


def test_pan_and_aadhaar_validation():
    tenant = create_tenant_and_admin("valkyc")
    headers = tenant["headers"]

    # 1. Invalid PAN format
    invalid_pan_resp = client.post(
        "/api/v1/users",
        data={
            "email": f"invalid-pan-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Test Pan Validation",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "staff",
            "pan_number": "INVALIDPAN123",
        },
        headers=headers,
    )
    assert invalid_pan_resp.status_code == 422
    assert "Invalid PAN card number" in invalid_pan_resp.text or "format" in invalid_pan_resp.text

    # 2. Invalid Aadhaar format (starts with 0)
    invalid_aadhaar_0 = client.post(
        "/api/v1/users",
        data={
            "email": f"invalid-aadhaar-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Test Aadhaar Zero",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "staff",
            "addhar_number": "012345678901",
        },
        headers=headers,
    )
    assert invalid_aadhaar_0.status_code == 422
    assert "cannot start with 0 or 1" in invalid_aadhaar_0.text

    # 3. Invalid Aadhaar format (less than 12 digits)
    invalid_aadhaar_short = client.post(
        "/api/v1/users",
        data={
            "email": f"invalid-aadhaar-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Test Aadhaar Short",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "staff",
            "addhar_number": "12345",
        },
        headers=headers,
    )
    assert invalid_aadhaar_short.status_code == 422
    assert "exactly 12 digits" in invalid_aadhaar_short.text

    # 4. Invalid Aadhaar format (all identical digits)
    invalid_aadhaar_identical = client.post(
        "/api/v1/users",
        data={
            "email": f"invalid-aadhaar-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Test Aadhaar Identical",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "staff",
            "addhar_number": "222222222222",
        },
        headers=headers,
    )
    assert invalid_aadhaar_identical.status_code == 422
    assert "identical digits" in invalid_aadhaar_identical.text


def test_create_user_missing_phone_returns_422():
    tenant = create_tenant_and_admin("mphone")
    headers = tenant["headers"]

    resp = client.post(
        "/api/v1/users",
        data={
            "email": f"no-phone-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "No Phone User",
            "password": "Password123!",
            "role": "staff",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "phone" in resp.text.lower()


def test_create_user_invalid_file_extension():
    tenant = create_tenant_and_admin("badext")
    headers = tenant["headers"]

    bad_file = io.BytesIO(b"executable file content")
    bad_file.name = "malicious.exe"

    resp = client.post(
        "/api/v1/users",
        data={
            "email": f"badfile-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Bad File User",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "cashier",
        },
        files={
            "pancard": ("malicious.exe", bad_file, "application/octet-stream"),
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "Invalid file type" in resp.text


def test_create_user_oversized_file():
    tenant = create_tenant_and_admin("bigfile")
    headers = tenant["headers"]

    big_content = b"0" * (6 * 1024 * 1024)  # 6 MB
    big_file = io.BytesIO(big_content)

    resp = client.post(
        "/api/v1/users",
        data={
            "email": f"bigfile-{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Big File User",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "cashier",
        },
        files={
            "profile_photo": ("avatar.png", big_file, "image/png"),
        },
        headers=headers,
    )
    assert resp.status_code == 413
    assert "exceeds maximum allowed size" in resp.text


@pytest.mark.parametrize(
    "invalid_email,expected_detail",
    [
        ("rohanpawar3333@gmail.comm", "gmail.comm"),
        ("testuser@gmail.con", "gmail.con"),
        ("testuser@yahoo.comm", "yahoo.comm"),
        ("employee@customdomain.comm", ".comm"),
        ("employee@customdomain.coom", ".coom"),
        ("employee@customdomain.cpm", ".cpm"),
    ],
)
def test_create_user_invalid_email_domain_typo_rejected(invalid_email, expected_detail):
    tenant = create_tenant_and_admin("bademail")
    headers = tenant["headers"]

    resp = client.post(
        "/api/v1/users",
        data={
            "email": invalid_email,
            "full_name": "Test Typo Email User",
            "password": "Password123!",
            "phone": "9876543210",
            "role": "staff",
        },
        headers=headers,
    )
    assert resp.status_code == 422, f"Expected 422 for {invalid_email}, got {resp.status_code}: {resp.text}"
    assert expected_detail in resp.text


