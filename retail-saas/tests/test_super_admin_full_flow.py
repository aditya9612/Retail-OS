import subprocess
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.store import Store
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.scripts.create_super_admin import create_super_admin_bootstrap
from app.services.super_admin_service import SuperAdminService

client = TestClient(app)


class TestSuperAdminCompleteFlow:
    """
    End-to-End Test Suite for the canonical flow:
    CLI -> Single Super Admin -> Super Admin creates Store Owner -> Store Owner has Multiple Stores -> Store Owner creates Role-based Users per Store
    """

    @pytest.fixture(autouse=True)
    def setup_single_super_admin(self):
        """Ensure clean state with exactly one Super Admin created via bootstrap/CLI logic."""
        db = SessionLocal()
        try:
            db.query(SuperAdmin).delete()
            db.commit()
        finally:
            db.close()

        # Create the single canonical Super Admin via bootstrap
        self.sa_email = "superadmin@retailos.canonical"
        self.sa_password = "SuperPassword@999!"
        self.sa_name = "Chief Super Admin"

        create_super_admin_bootstrap(
            email=self.sa_email,
            full_name=self.sa_name,
            password=self.sa_password,
            phone="9876543210",
        )

        # Ensure default plan (Plan 1) has entitlements configured
        from app.models.saas_plan_entitlement import SaaSPlanEntitlement
        db = SessionLocal()
        try:
            for dim, val in [("stores", 10), ("users", 25), ("products", 5000)]:
                existing_ent = db.query(SaaSPlanEntitlement).filter(
                    SaaSPlanEntitlement.plan_id == 1,
                    SaaSPlanEntitlement.dimension == dim,
                ).first()
                if not existing_ent:
                    db.add(SaaSPlanEntitlement(plan_id=1, dimension=dim, value=val, is_unlimited=False))
            db.commit()
        finally:
            db.close()

        yield

    def test_step1_only_one_super_admin_allowed_and_cli_only(self, monkeypatch):
        """1. Only ONE Super Admin allowed and CLI rejects second Super Admin."""
        import io
        captured_err = io.StringIO()
        monkeypatch.setattr(sys, "stderr", captured_err)

        # Attempt to create another Super Admin via CLI bootstrap must exit with code 1
        with pytest.raises(SystemExit) as exc:
            create_super_admin_bootstrap(
                email="another_super_admin@retailos.canonical",
                full_name="Second Super Admin",
                password="AnotherPassword@123!",
                phone="9876543211",
            )
        assert exc.value.code == 1
        err_msg = captured_err.getvalue()
        assert "Only ONE Super Admin is permitted" in err_msg

        # Attempting via service also fails with ConflictException
        from app.core.exceptions import ConflictException
        from app.schemas.super_admin import SuperAdminCreate
        db = SessionLocal()
        try:
            with pytest.raises(ConflictException) as exc_info:
                SuperAdminService(db).create_super_admin(
                    SuperAdminCreate(
                        email="third_sa@retailos.canonical",
                        full_name="Third SA",
                        password="ThirdPassword@123!",
                    )
                )
            assert "Only ONE Super Admin is permitted" in str(exc_info.value.detail)
        finally:
            db.close()

    def test_step2_public_and_api_super_admin_creation_completely_removed(self):
        """2. Public/API Super Admin creation endpoint POST /api/v1/super-admins is removed."""
        payload = {
            "email": "api_hacker@example.com",
            "full_name": "API Hacker",
            "password": "Password@123!",
        }
        res = client.post("/api/v1/super-admins", json=payload)
        # Endpoint removed from router -> 405 Method Not Allowed or 404 Not Found
        assert res.status_code in (404, 405)

    def test_step3_to_step7_full_lifecycle(self):
        """
        Step 3: Super Admin logs in and creates Store Owner
        Step 4: Store Owner has multiple stores
        Step 5: Store Owner access is isolated strictly to their own stores
        Step 6: Store Owner creates role-based users per store
        Step 7: Enforce proper store-level & tenant authorization
        """
        # ==========================================
        # STEP 3: SUPER ADMIN LOGIN & CREATE STORE OWNER
        # ==========================================
        sa_login_res = client.post(
            "/api/v1/super-admins/login",
            json={"email": self.sa_email, "password": self.sa_password},
        )
        assert sa_login_res.status_code == 200
        sa_token = sa_login_res.json()["access_token"]
        sa_headers = {"Authorization": f"Bearer {sa_token}"}

        # Super Admin creates Store Owner 1
        uid_1 = uuid.uuid4().hex[:6]
        owner1_email = f"owner1_{uid_1}@storecorp.com"
        owner1_password = "OwnerPassword@123!"
        store1_name = f"Apex Retail Group {uid_1}"

        name_suffix1 = "".join([c for c in uid_1 if c.isalpha()] or ["Alpha"])
        create_owner1_payload = {
            "store_name": store1_name,
            "owner_name": f"Aditya Owner {name_suffix1}",
            "owner_email": owner1_email,
            "password": owner1_password,
            "owner_phone": "9812345678",
            "address": "100 MG Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
        }

        owner1_res = client.post(
            "/api/v1/super-admins/store-owners",
            json=create_owner1_payload,
            headers=sa_headers,
        )
        assert owner1_res.status_code == 201, f"Failed: {owner1_res.text}"
        owner1_data = owner1_res.json()
        tenant1_id = owner1_data["id"]
        assert owner1_data["name"] == store1_name
        assert owner1_data["owner"]["email"] == owner1_email

        # Also create Store Owner 2 (to verify isolation between store owners)
        uid_2 = uuid.uuid4().hex[:6]
        name_suffix2 = "".join([c for c in uid_2 if c.isalpha()] or ["Beta"])
        owner2_email = f"owner2_{uid_2}@rivalretail.com"
        owner2_password = "OwnerPassword@456!"
        store2_name = f"Beacon Supermarket {uid_2}"

        create_owner2_payload = {
            "store_name": store2_name,
            "owner_name": f"Rajesh Owner {name_suffix2}",
            "owner_email": owner2_email,
            "password": owner2_password,
            "owner_phone": "9823456789",
            "address": "50 FC Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411004",
        }

        owner2_res = client.post(
            "/api/v1/super-admins/store-owners",
            json=create_owner2_payload,
            headers=sa_headers,
        )
        assert owner2_res.status_code == 201
        tenant2_id = owner2_res.json()["id"]

        # ==========================================
        # STEP 4: STORE OWNER LOGINS & CREATES MULTIPLE STORES
        # ==========================================
        owner1_login = client.post(
            "/api/v1/auth/login",
            json={"email": owner1_email, "password": owner1_password},
        )
        assert owner1_login.status_code == 200
        owner1_token = owner1_login.json()["access_token"]
        owner1_headers = {"Authorization": f"Bearer {owner1_token}"}

        # Store Owner 1 creates Store 2 (Branch - Pune West)
        store_branch1_res = client.post(
            "/api/v1/stores/",
            json={
                "name": f"Apex Kothrud Branch {uid_1}",
                "code": f"APX-KOT-{uid_1[:4].upper()}",
                "address": "Paud Road",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411038",
                "phone": "9812345679",
            },
            headers=owner1_headers,
        )
        assert store_branch1_res.status_code == 201
        store_branch1_id = store_branch1_res.json()["id"]

        # Store Owner 1 creates Store 3 (Branch - Pune East)
        store_branch2_res = client.post(
            "/api/v1/stores/",
            json={
                "name": f"Apex Viman Nagar {uid_1}",
                "code": f"APX-VIM-{uid_1[:4].upper()}",
                "address": "Phoenix Road",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411014",
                "phone": "9812345680",
            },
            headers=owner1_headers,
        )
        assert store_branch2_res.status_code == 201
        store_branch2_id = store_branch2_res.json()["id"]

        # Verify Store Owner 1 has multiple stores
        owner1_stores_res = client.get("/api/v1/stores/", headers=owner1_headers)
        assert owner1_stores_res.status_code == 200
        owner1_store_list = owner1_stores_res.json()
        owner1_store_ids = {s["id"] for s in owner1_store_list}
        assert store_branch1_id in owner1_store_ids
        assert store_branch2_id in owner1_store_ids
        assert len(owner1_store_list) >= 3  # Initial MAIN store + 2 branches

        # Get initial MAIN store ID
        main_store_1_id = next(s["id"] for s in owner1_store_list if s["is_main"] is True)

        # ==========================================
        # STEP 5: STORE OWNER ACCESS IS ISOLATED
        # ==========================================
        owner2_login = client.post(
            "/api/v1/auth/login",
            json={"email": owner2_email, "password": owner2_password},
        )
        assert owner2_login.status_code == 200
        owner2_headers = {"Authorization": f"Bearer {owner2_login.json()['access_token']}"}

        # Store Owner 2 lists their stores
        owner2_stores_res = client.get("/api/v1/stores/", headers=owner2_headers)
        assert owner2_stores_res.status_code == 200
        owner2_store_ids = {s["id"] for s in owner2_stores_res.json()}

        # Disjoint stores: Owner 1 and Owner 2 cannot see each other's stores
        assert owner1_store_ids.isdisjoint(owner2_store_ids)

        # Store Owner 2 cannot get Store Owner 1's store
        cross_get_res = client.get(f"/api/v1/stores/{main_store_1_id}", headers=owner2_headers)
        assert cross_get_res.status_code in (403, 404)

        # Store Owner 2 cannot delete Store Owner 1's store
        cross_del_res = client.delete(f"/api/v1/stores/{main_store_1_id}", headers=owner2_headers)
        assert cross_del_res.status_code in (403, 404)

        # ==========================================
        # STEP 6: STORE OWNER CREATES ROLE-BASED USERS PER STORE
        # ==========================================
        # Get roles for Tenant 1
        roles_res = client.get("/api/v1/roles", headers=owner1_headers)
        assert roles_res.status_code == 200
        roles_list = roles_res.json()
        roles_map = {r["name"].lower(): r["id"] for r in roles_list}
        manager_role_id = roles_map.get("manager")
        staff_role_id = roles_map.get("staff")
        assert manager_role_id is not None
        assert staff_role_id is not None

        # 6a. Create Store Manager for Branch 1 (Kothrud)
        mgr_email = f"mgr_kothrud_{uid_1}@storecorp.com"
        mgr_password = "MgrPassword@123!"
        # Verify removed store users endpoints return 404
        assert client.get(f"/api/v1/stores/{store_branch1_id}/users", headers=owner1_headers).status_code == 404
        assert client.post(f"/api/v1/stores/{store_branch1_id}/users", headers=owner1_headers, json={}).status_code == 404

        create_mgr_res = client.post(
            "/api/v1/users",
            json={
                "email": mgr_email,
                "full_name": f"Kothrud Manager {name_suffix1}",
                "password": mgr_password,
                "role_id": manager_role_id,
                "store_id": store_branch1_id,
                "phone": "9811122233",
            },
            headers=owner1_headers,
        )
        assert create_mgr_res.status_code == 201, f"Failed creating manager: {create_mgr_res.text}"
        mgr_user = create_mgr_res.json()
        assert mgr_user["store_id"] == store_branch1_id
        assert mgr_user["role_id"] == manager_role_id

        # 6b. Create Cashier/Staff for Branch 1 (Kothrud) via /api/v1/users with store_id
        staff_kothrud_email = f"staff_kothrud_{uid_1}@storecorp.com"
        staff_password = "StaffPassword@123!"
        create_staff_res = client.post(
            "/api/v1/users",
            json={
                "email": staff_kothrud_email,
                "full_name": f"Kothrud Cashier {name_suffix1}",
                "password": staff_password,
                "role_id": staff_role_id,
                "store_id": store_branch1_id,
                "phone": "9811122234",
            },
            headers=owner1_headers,
        )
        assert create_staff_res.status_code == 201, f"Failed creating staff: {create_staff_res.text}"
        staff_user = create_staff_res.json()
        assert staff_user["store_id"] == store_branch1_id

        # 6c. Create Staff for Branch 2 (Viman Nagar)
        staff_viman_email = f"staff_viman_{uid_1}@storecorp.com"
        create_viman_staff_res = client.post(
            "/api/v1/users",
            json={
                "email": staff_viman_email,
                "full_name": f"Viman Staff {name_suffix1}",
                "password": staff_password,
                "role_id": staff_role_id,
                "store_id": store_branch2_id,
                "phone": "9811122235",
            },
            headers=owner1_headers,
        )
        assert create_viman_staff_res.status_code == 201, f"Failed creating viman staff: {create_viman_staff_res.text}"
        assert create_viman_staff_res.json()["store_id"] == store_branch2_id

        # List users specifically for Branch 1
        branch1_users_res = client.get(f"/api/v1/users?store_id={store_branch1_id}", headers=owner1_headers)
        assert branch1_users_res.status_code == 200
        b1_users = branch1_users_res.json()
        b1_emails = {u["email"] for u in b1_users}
        assert mgr_email in b1_emails
        assert staff_kothrud_email in b1_emails
        assert staff_viman_email not in b1_emails  # Viman staff belongs to Branch 2, not Branch 1

        # ==========================================
        # STEP 7: PROPER STORE-LEVEL AUTHORIZATION ENFORCEMENT
        # ==========================================
        # Login as Kothrud Manager (store_id = store_branch1_id)
        mgr_login = client.post(
            "/api/v1/auth/login",
            json={"email": mgr_email, "password": mgr_password},
        )
        assert mgr_login.status_code == 200
        mgr_token = mgr_login.json()["access_token"]
        mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

        # 7a. Store Manager sees ONLY their assigned store
        mgr_stores = client.get("/api/v1/stores/", headers=mgr_headers)
        assert mgr_stores.status_code == 200
        mgr_store_list = mgr_stores.json()
        assert len(mgr_store_list) == 1
        assert mgr_store_list[0]["id"] == store_branch1_id

        # 7b. Store Manager CANNOT access Branch 2 (Viman Nagar)
        cross_store_access = client.get(f"/api/v1/stores/{store_branch2_id}", headers=mgr_headers)
        assert cross_store_access.status_code == 403
        assert "Access denied" in cross_store_access.text

        # 7c. Store Manager CANNOT create new stores
        mgr_create_store = client.post(
            "/api/v1/stores/",
            json={"name": "Illegal Branch", "code": "ILLEGAL-01"},
            headers=mgr_headers,
        )
        assert mgr_create_store.status_code in (403, 422)

        # 7d. Store Manager CANNOT delete stores
        mgr_del_store = client.delete(f"/api/v1/stores/{store_branch1_id}", headers=mgr_headers)
        assert mgr_del_store.status_code in (403, 401)

        # 7e. Store Manager CANNOT access users of Branch 2
        mgr_cross_users = client.get(f"/api/v1/users?store_id={store_branch2_id}", headers=mgr_headers)
        assert mgr_cross_users.status_code == 403
