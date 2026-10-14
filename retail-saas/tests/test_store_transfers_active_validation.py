import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.product import Product

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


def test_cannot_transfer_to_or_from_inactive_deleted_store():
    tenant_info = create_tenant_and_admin("trfactive")
    headers = tenant_info["headers"]
    tenant_id = tenant_info["tenant_id"]

    db = SessionLocal()
    try:
        # Create Store 1 (Active)
        store1 = Store(
            name=f"Active Store 1 {uuid.uuid4().hex[:4]}",
            code=f"ACT1-{uuid.uuid4().hex[:4].upper()}",
            tenant_id=tenant_id,
            is_active=True,
        )
        # Create Store 2 (Inactive / Deleted)
        store2 = Store(
            name=f"Inactive Store 2 {uuid.uuid4().hex[:4]}",
            code=f"INACT2-{uuid.uuid4().hex[:4].upper()}",
            tenant_id=tenant_id,
            is_active=False,
        )
        # Create Store 3 (Active)
        store3 = Store(
            name=f"Active Store 3 {uuid.uuid4().hex[:4]}",
            code=f"ACT3-{uuid.uuid4().hex[:4].upper()}",
            tenant_id=tenant_id,
            is_active=True,
        )
        # Create active product
        product1 = Product(
            name="Test Milk 1L",
            sku=f"SKU-MILK-{uuid.uuid4().hex[:6]}",
            selling_price=50.0,
            tenant_id=tenant_id,
            is_active=True,
        )
        # Create inactive product
        product2 = Product(
            name="Deactivated Item",
            sku=f"SKU-INACT-{uuid.uuid4().hex[:6]}",
            selling_price=50.0,
            tenant_id=tenant_id,
            is_active=False,
        )
        db.add_all([store1, store2, store3, product1, product2])
        db.commit()
        s1_id = store1.id
        s2_id = store2.id
        s3_id = store3.id
        p1_id = product1.id
        p2_id = product2.id
    finally:
        db.close()

    # 1. Attempt transfer to inactive destination store (Store 2) -> Must fail with 400
    resp_dst_inactive = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert resp_dst_inactive.status_code == 400, resp_dst_inactive.text
    assert "Destination store is inactive or has been deleted" in resp_dst_inactive.json()["detail"]

    # 2. Attempt transfer from inactive source store (Store 2) -> Must fail with 400
    resp_src_inactive = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s2_id,
            "destination_store_id": s3_id,
            "items": [{"product_id": p1_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert resp_src_inactive.status_code == 400, resp_src_inactive.text
    assert "Source store is inactive or has been deleted" in resp_src_inactive.json()["detail"]

    # 3. Attempt transfer with inactive product -> Must fail with 400
    resp_prod_inactive = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s3_id,
            "items": [{"product_id": p2_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert resp_prod_inactive.status_code == 400, resp_prod_inactive.text
    assert "inactive or deleted" in resp_prod_inactive.json()["detail"]

    # 4. Valid transfer between active Store 1 and Store 3 -> Succeeds with 201
    resp_valid = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s3_id,
            "items": [{"product_id": p1_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert resp_valid.status_code == 201, resp_valid.text
    transfer_id = resp_valid.json()["id"]

    # 5. Now deactivate Store 3 and try to approve the transfer -> Must fail with 400
    db = SessionLocal()
    try:
        s3 = db.query(Store).filter(Store.id == s3_id).first()
        s3.is_active = False
        db.commit()
    finally:
        db.close()

    resp_approve = client.put(
        f"/api/v1/store-transfers/{transfer_id}/approve",
        headers=headers,
    )
    assert resp_approve.status_code == 400, resp_approve.text
    assert "Destination store is inactive or has been deleted" in resp_approve.json()["detail"]
