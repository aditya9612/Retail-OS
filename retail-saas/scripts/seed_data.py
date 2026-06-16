"""Seed sample data for development."""

from decimal import Decimal

from app.core.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.store import Store
from app.models.tenant import Tenant
from app.services.auth_service import AuthService


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Tenant).filter(Tenant.slug == "demo").first()
        if existing:
            print("Demo tenant already exists")
            return

        user = AuthService(db).register_tenant(
            tenant_name="Demo Store",
            slug="demo",
            email="admin@demo.com",
            admin_name="Demo Admin",
            password="admin123",
        )

        store = Store(
            tenant_id=user.tenant_id,
            name="Main Store",
            code="MAIN",
            city="Pune",
            state="Maharashtra",
            gstin="27AAAAA0000A1Z5",
        )
        db.add(store)
        db.flush()

        category = Category(tenant_id=user.tenant_id, name="General")
        db.add(category)
        db.flush()

        products = [
            Product(
                tenant_id=user.tenant_id,
                category_id=category.id,
                name="Sample Product A",
                sku="SKU-001",
                barcode="8901234567890",
                price=Decimal("199.00"),
                cost_price=Decimal("120.00"),
                hsn_code="6109",
                gst_rate=Decimal("12.00"),
            ),
            Product(
                tenant_id=user.tenant_id,
                category_id=category.id,
                name="Sample Product B",
                sku="SKU-002",
                barcode="8901234567891",
                price=Decimal("499.00"),
                cost_price=Decimal("350.00"),
                hsn_code="6109",
                gst_rate=Decimal("18.00"),
            ),
        ]
        db.add_all(products)
        db.commit()
        print(f"Seeded tenant_id={user.tenant_id}, store_id={store.id}, products={len(products)}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
