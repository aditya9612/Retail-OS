import io
import os
import subprocess
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import (
    blacklist_token,
    create_super_admin_access_token,
    create_super_admin_refresh_token,
    get_password_hash,
    verify_password,
)
from app.models.super_admin import SuperAdmin
from app.scripts.create_super_admin import create_super_admin_bootstrap

client = TestClient(app)


def _get_error_msg(res) -> str:
    body = res.json()
    detail = body.get("detail", "")
    if isinstance(detail, dict):
        return detail.get("message", "")
    return str(detail)


class TestSuperAdminBootstrap:
    def test_bootstrap_creates_first_super_admin(self, monkeypatch):
        uid = uuid.uuid4().hex[:8]
        name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
        email = f"boot_{uid}@example.com"
        full_name = f"Bootstrap Admin {name_suffix}"
        password = "BootPassword@987!"

        # Capture output
        captured_out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        create_super_admin_bootstrap(
            email=email,
            full_name=full_name,
            password=password,
            phone="9876543210",
        )

        output = captured_out.getvalue()
        assert f"Super Admin created successfully: {email}" in output
        assert password not in output  # Password must NEVER be printed

        # Verify in DB
        db = SessionLocal()
        try:
            sa = db.query(SuperAdmin).filter(SuperAdmin.email == email).first()
            assert sa is not None
            assert sa.full_name == full_name
            assert sa.is_active is True
            assert sa.hashed_password != password
            assert verify_password(password, sa.hashed_password)
        finally:
            db.close()

    def test_bootstrap_duplicate_email_rejected(self, monkeypatch):
        uid = uuid.uuid4().hex[:8]
        name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
        email = f"dup_{uid}@example.com"
        password = "BootPassword@987!"

        # Create first time
        create_super_admin_bootstrap(
            email=email,
            full_name=f"Admin {name_suffix}",
            password=password,
        )

        captured_err = io.StringIO()
        monkeypatch.setattr(sys, "stderr", captured_err)

        # Second attempt with same email must exit non-zero
        with pytest.raises(SystemExit) as exc:
            create_super_admin_bootstrap(
                email=email,
                full_name=f"Duplicate {name_suffix}",
                password=password,
            )

        assert exc.value.code == 1
        err_out = captured_err.getvalue()
        assert "already exists" in err_out

    def test_bootstrap_does_not_overwrite_or_reactivate_inactive(self, monkeypatch):
        uid = uuid.uuid4().hex[:8]
        email = f"inactive_{uid}@example.com"
        orig_pw = "OriginalPass@123!"

        # Pre-seed inactive super admin
        db = SessionLocal()
        try:
            sa = SuperAdmin(
                email=email,
                full_name="Inactive Admin",
                hashed_password=get_password_hash(orig_pw),
                is_active=False,
            )
            db.add(sa)
            db.commit()
            orig_hash = sa.hashed_password
        finally:
            db.close()

        captured_err = io.StringIO()
        monkeypatch.setattr(sys, "stderr", captured_err)

        # Attempt to run bootstrap on the same email
        with pytest.raises(SystemExit) as exc:
            create_super_admin_bootstrap(
                email=email,
                full_name="Overwriting Attempt",
                password="NewPassword@999!",
            )

        assert exc.value.code == 1
        assert "already exists" in captured_err.getvalue()

        # Verify DB record was NOT modified or reactivated
        verify_db = SessionLocal()
        try:
            sa_check = verify_db.query(SuperAdmin).filter(SuperAdmin.email == email).first()
            assert sa_check is not None
            assert sa_check.is_active is False  # Must remain inactive
            assert sa_check.hashed_password == orig_hash  # Password must NOT be overwritten
            assert sa_check.full_name == "Inactive Admin"
        finally:
            verify_db.close()

    def test_bootstrap_password_validation_rejection(self, monkeypatch):
        uid = uuid.uuid4().hex[:8]
        email = f"weak_{uid}@example.com"
        weak_password = "weak"  # Fails min_length and complexity rules

        captured_err = io.StringIO()
        monkeypatch.setattr(sys, "stderr", captured_err)

        with pytest.raises(SystemExit) as exc:
            create_super_admin_bootstrap(
                email=email,
                full_name="Weak Pass Admin",
                password=weak_password,
            )

        assert exc.value.code == 1
        assert "Validation error" in captured_err.getvalue()

    def test_bootstrap_cli_execution_with_env_password(self):
        uid = uuid.uuid4().hex[:8]
        name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
        email = f"cli_{uid}@example.com"
        full_name = f"CLI Admin {name_suffix}"
        password = "CliPassword@123!"

        env = os.environ.copy()
        env["SUPER_ADMIN_PASSWORD"] = password

        cmd = [
            sys.executable,
            "-m",
            "app.scripts.create_super_admin",
            "--email",
            email,
            "--full-name",
            full_name,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert f"Super Admin created successfully: {email}" in result.stdout
        assert password not in result.stdout
        assert password not in result.stderr


class TestSuperAdminSecurityAuthorization:
    @pytest.fixture
    def active_super_admin(self):
        uid = uuid.uuid4().hex[:8]
        name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
        email = f"sa_sec_{uid}@example.com"
        password = "SuperPassword@123!"
        db = SessionLocal()
        try:
            sa = SuperAdmin(
                email=email,
                full_name=f"Security SA {name_suffix}",
                hashed_password=get_password_hash(password),
                is_active=True,
            )
            db.add(sa)
            db.commit()
            db.refresh(sa)
            sa_id = sa.id
        finally:
            db.close()

        token_data = {"sub": str(sa_id), "role": "SUPERADMIN"}
        access_token = create_super_admin_access_token(token_data)
        refresh_token = create_super_admin_refresh_token(token_data)

        return {
            "id": sa_id,
            "email": email,
            "password": password,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def test_anonymous_cannot_create_super_admin(self):
        payload = {
            "email": "anon_attacker@example.com",
            "full_name": "Anon Attacker",
            "password": "Password@123!",
        }
        res = client.post("/api/v1/super-admins", json=payload)
        assert res.status_code == 401

    def test_tenant_jwt_rejected_on_super_admin_api(self):
        # Create tenant JWT (type='access', role='tenant_admin')
        from app.core.security import create_access_token
        tenant_token = create_access_token({"sub": "999", "tenant_id": 1, "role": "admin"})

        headers = {"Authorization": f"Bearer {tenant_token}"}
        res = client.get("/api/v1/super-admins/me", headers=headers)
        assert res.status_code == 401
        msg = _get_error_msg(res)
        assert "Invalid SuperAdmin token type" in msg

    def test_valid_super_admin_access(self, active_super_admin):
        headers = {"Authorization": f"Bearer {active_super_admin['access_token']}"}
        res = client.get("/api/v1/super-admins/me", headers=headers)
        assert res.status_code == 200
        assert res.json()["email"] == active_super_admin["email"]

    def test_inactive_super_admin_rejected(self, active_super_admin):
        db = SessionLocal()
        try:
            sa = db.query(SuperAdmin).filter(SuperAdmin.id == active_super_admin["id"]).first()
            sa.is_active = False
            db.commit()
        finally:
            db.close()

        headers = {"Authorization": f"Bearer {active_super_admin['access_token']}"}
        res = client.get("/api/v1/super-admins/me", headers=headers)
        assert res.status_code == 401

    def test_blacklisted_token_rejected(self, active_super_admin):
        # Blacklist the token
        blacklist_token(active_super_admin["access_token"])

        headers = {"Authorization": f"Bearer {active_super_admin['access_token']}"}
        res = client.get("/api/v1/super-admins/me", headers=headers)
        assert res.status_code == 401
        msg = _get_error_msg(res)
        assert "revoked" in msg.lower()

    def test_refresh_token_cannot_be_used_as_access_token(self, active_super_admin):
        headers = {"Authorization": f"Bearer {active_super_admin['refresh_token']}"}
        res = client.get("/api/v1/super-admins/me", headers=headers)
        assert res.status_code == 401

    def test_access_token_cannot_be_used_as_refresh_token(self, active_super_admin):
        res = client.post(
            "/api/v1/super-admins/refresh",
            json={"refresh_token": active_super_admin["access_token"]},
        )
        assert res.status_code == 401
        msg = _get_error_msg(res)
        assert "Invalid Super Admin refresh token" in msg

    def test_self_deactivation_protection(self, active_super_admin):
        headers = {"Authorization": f"Bearer {active_super_admin['access_token']}"}
        res = client.patch(
            f"/api/v1/super-admins/{active_super_admin['id']}/status",
            json={"is_active": False},
            headers=headers,
        )
        assert res.status_code == 401
        msg = _get_error_msg(res)
        assert "cannot deactivate your own account" in msg

    def test_self_deletion_protection(self, active_super_admin):
        headers = {"Authorization": f"Bearer {active_super_admin['access_token']}"}
        res = client.delete(
            f"/api/v1/super-admins/{active_super_admin['id']}",
            headers=headers,
        )
        assert res.status_code == 409
        msg = _get_error_msg(res)
        assert "cannot delete your own" in msg.lower()
