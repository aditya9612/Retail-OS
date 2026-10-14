from datetime import datetime, time
from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order
from app.models.pos_shift import POSShift
from app.models.product import Product
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.models.user import User
from app.repositories.store_repo import StoreRepository
from app.schemas.store import StoreCreate, StoreUpdate
from app.services.saas_entitlement_service import SaaSEntitlementService


class StoreService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)

    def _unset_other_main_stores(self, tenant_id: int, exclude_store_id: int | None = None) -> int | None:
        """Demote existing main store(s) to guarantee only one main store exists per tenant."""
        query = self.db.query(Store).filter(
            Store.tenant_id == tenant_id,
            Store.is_main == True,
        )
        if exclude_store_id is not None:
            query = query.filter(Store.id != exclude_store_id)

        prev = query.first()
        prev_id = prev.id if prev else None
        query.update({"is_main": False}, synchronize_session=False)
        return prev_id

    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:

        if self.repo.get_by_name(data.name, tenant_id):
            raise ConflictException("Store name already exists")

        if self.repo.get_by_code(data.code, tenant_id):
            raise ConflictException("Store code already exists")

        # Atomic tenant lock & quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.STORES,
            requested_amount=1,
            lock_tenant=True,
        )

        if data.is_main:
            self._unset_other_main_stores(tenant_id)

        store_data = data.model_dump()
        # Prevent is_warehouse property setter from overriding is_main
        store_data.pop("is_warehouse", None)

        store = Store(
            tenant_id=tenant_id,
            **store_data
        )

        store = self.repo.create(store)
        self.db.commit()
        self.db.refresh(store)
        return store

    def get_store(self, tenant_id: int, store_id: int, include_inactive: bool = False) -> Store:

        store = self.repo.get_by_id(store_id, tenant_id, include_inactive=include_inactive)

        if not store:
            raise NotFoundException("Store not found")

        return store

    def list_stores(
        self,
        tenant_id: int,
        store_id: int | None = None,
        include_inactive: bool = False,
        search: str | None = None,
        is_warehouse: bool | None = None,
    ) -> list[Store]:
        if store_id is not None:
            store = self.repo.get_by_id(store_id, tenant_id, include_inactive=include_inactive)
            if not store:
                return []
            if search and search.strip():
                term = search.strip().lower()
                matches = (
                    term in (store.name or "").lower()
                    or term in (store.code or "").lower()
                    or term in (store.city or "").lower()
                )
                if not matches:
                    return []
            if is_warehouse is not None and store.is_warehouse != is_warehouse:
                return []
            return [store]
        return self.repo.list_stores(
            tenant_id=tenant_id,
            include_inactive=include_inactive,
            search=search,
            is_warehouse=is_warehouse,
        )

    def update_store(self, tenant_id: int, store_id: int, data: StoreUpdate) -> Store:

        store = self.get_store(tenant_id, store_id, include_inactive=True)

        update_data = data.model_dump(exclude_unset=True)

        # Quota check only when reactivating: False -> True
        if "is_active" in update_data and not store.is_active and update_data["is_active"] is True:
            entitlement_svc = SaaSEntitlementService(self.db)
            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.STORES,
                requested_amount=1,
                lock_tenant=True,
            )

        if "name" in update_data:
            existing = self.repo.get_by_name(update_data["name"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store name already exists")

        if "code" in update_data:
            existing = self.repo.get_by_code(update_data["code"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store code already exists")

        if "is_warehouse" in update_data:
            wh_val = update_data.pop("is_warehouse")
            if "is_main" not in update_data and wh_val is not None:
                update_data["is_main"] = not wh_val

        if update_data.get("is_main") is True:
            self._unset_other_main_stores(tenant_id, exclude_store_id=store_id)

        for key, value in update_data.items():
            setattr(store, key, value)

        return self.repo.update(store)

    def delete_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.get_store(tenant_id, store_id)

        inventory_exists = (
            self.db.query(Inventory)
            .filter(
                Inventory.store_id == store_id,
                Inventory.tenant_id == tenant_id
            )
            .first()
        )

        if inventory_exists:
            raise ConflictException(
                "Cannot delete store because inventory exists"
            )

        movement_exists = (
            self.db.query(StockMovement)
            .filter(
                StockMovement.store_id == store_id,
                StockMovement.tenant_id == tenant_id
            )
            .first()
        )

        if movement_exists:
            raise ConflictException(
                "Cannot delete store because stock movements exist"
            )

        return self.repo.soft_delete(store)

    def set_main_store(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)
        if not store.is_active:
            raise ConflictException("Cannot set an inactive store as main store. Please activate it first.")

        prev_id = self._unset_other_main_stores(tenant_id, exclude_store_id=store_id)
        store.is_main = True
        self.db.commit()
        self.db.refresh(store)
        return {
            "success": True,
            "message": "Store designated as main store successfully",
            "store_id": store.id,
            "previous_main_store_id": prev_id,
            "is_main": True,
        }

    def activate_store(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)
        if store.is_active:
            return {
                "success": True,
                "message": "Store is already active",
                "store_id": store.id,
                "is_active": True,
            }

        # Quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.STORES,
            requested_amount=1,
            lock_tenant=True,
        )

        store.is_active = True
        self.db.commit()
        self.db.refresh(store)
        return {
            "success": True,
            "message": "Store activated successfully",
            "store_id": store.id,
            "is_active": True,
        }

    def deactivate_store(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)
        if not store.is_active:
            return {
                "success": True,
                "message": "Store is already deactivated",
                "store_id": store.id,
                "is_active": False,
            }

        if store.is_main:
            # Check if there are other active stores
            other_active = self.db.query(Store).filter(
                Store.tenant_id == tenant_id,
                Store.id != store_id,
                Store.is_active == True,
            ).first()
            if other_active:
                raise ConflictException(
                    "Cannot deactivate the main store. Please designate another store as main first."
                )

        active_shifts = (
            self.db.query(POSShift)
            .filter(
                POSShift.store_id == store_id,
                POSShift.tenant_id == tenant_id,
                POSShift.status == "open",
            )
            .count()
        )
        if active_shifts > 0:
            raise ConflictException(
                f"Cannot deactivate store with {active_shifts} active POS shift(s). Please close open shifts first."
            )

        store.is_active = False
        self.db.commit()
        self.db.refresh(store)
        return {
            "success": True,
            "message": "Store deactivated successfully",
            "store_id": store.id,
            "is_active": False,
        }

    def get_store_staff(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)

        users = (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.store_id == store_id,
                User.is_deleted == False,
            )
            .order_by(User.id.asc())
            .all()
        )

        staff_list = []
        for u in users:
            role_name = u.role.name if getattr(u, "role", None) else "staff"
            staff_list.append(
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "phone": u.phone,
                    "role": role_name,
                    "is_active": u.is_active,
                }
            )

        return {
            "store_id": store.id,
            "store_name": store.name,
            "total_staff": len(staff_list),
            "staff": staff_list,
        }

    def get_store_summary(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)

        today_start = datetime.combine(datetime.utcnow().date(), time.min)

        # Today's sales and orders
        today_stats = (
            self.db.query(
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")),
                func.count(Order.id),
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.store_id == store_id,
                Order.created_at >= today_start,
                Order.status != "cancelled",
            )
            .first()
        )
        today_sales = today_stats[0] if today_stats else Decimal("0.00")
        today_orders = today_stats[1] if today_stats else 0

        # Lifetime orders count
        total_orders = (
            self.db.query(func.count(Order.id))
            .filter(
                Order.tenant_id == tenant_id,
                Order.store_id == store_id,
            )
            .scalar()
            or 0
        )

        # Total assigned staff
        staff_count = (
            self.db.query(func.count(User.id))
            .filter(
                User.tenant_id == tenant_id,
                User.store_id == store_id,
                User.is_deleted == False,
            )
            .scalar()
            or 0
        )

        # Active POS shifts
        open_shifts = (
            self.db.query(func.count(POSShift.id))
            .filter(
                POSShift.tenant_id == tenant_id,
                POSShift.store_id == store_id,
                POSShift.status == "open",
            )
            .scalar()
            or 0
        )

        # Inventory metrics
        inv_items = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == store_id,
            )
            .all()
        )
        total_inv = len(inv_items)
        low_stock = sum(
            1
            for item in inv_items
            if Decimal(str(item.quantity)) <= item.min_stock_level
            and Decimal(str(item.quantity)) > 0
        )
        out_of_stock = sum(
            1 for item in inv_items if Decimal(str(item.quantity)) <= 0
        )

        return {
            "store_id": store.id,
            "store_name": store.name,
            "code": store.code,
            "is_main": store.is_main,
            "is_active": store.is_active,
            "is_warehouse": store.is_warehouse,
            "today_sales_amount": Decimal(str(today_sales)),
            "today_orders_count": today_orders,
            "total_orders_count": total_orders,
            "total_staff_count": staff_count,
            "active_pos_shifts_count": open_shifts,
            "total_inventory_items": total_inv,
            "low_stock_items_count": low_stock,
            "out_of_stock_items_count": out_of_stock,
        }

    def get_store_inventory_summary(self, tenant_id: int, store_id: int) -> dict:
        store = self.get_store(tenant_id, store_id, include_inactive=True)

        results = (
            self.db.query(
                Inventory.quantity,
                Inventory.min_stock_level,
                Product.selling_price,
            )
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == store_id,
            )
            .all()
        )

        total_skus = len(results)
        total_quantity = Decimal("0.00")
        total_value = Decimal("0.00")
        in_stock_count = 0
        low_stock_count = 0
        out_of_stock_count = 0

        for qty, min_stock, price in results:
            q = Decimal(str(qty or 0))
            p = Decimal(str(price or 0))
            total_quantity += q
            total_value += q * p

            if q <= 0:
                out_of_stock_count += 1
            elif q <= (min_stock or 0):
                low_stock_count += 1
            else:
                in_stock_count += 1

        return {
            "store_id": store.id,
            "store_name": store.name,
            "total_skus": total_skus,
            "total_stock_quantity": total_quantity,
            "total_stock_value": total_value,
            "in_stock_skus": in_stock_count,
            "low_stock_skus": low_stock_count,
            "out_of_stock_skus": out_of_stock_count,
        }