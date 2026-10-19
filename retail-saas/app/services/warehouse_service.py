from decimal import Decimal
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import NotFoundException
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.models.warehouse import Warehouse
from app.repositories.warehouse_repo import WarehouseRepository
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseUpdate,
)


class WarehouseService:

    def __init__(self, db):
        self.db = db
        self.repo = WarehouseRepository(db)

    def _attach_store_name(self, warehouse: Warehouse) -> Warehouse:
        if warehouse and warehouse.store_id:
            store = (
                self.db.query(Store)
                .filter(Store.id == warehouse.store_id)
                .first()
            )
            warehouse.store_name = store.name if store else None
        elif warehouse:
            warehouse.store_name = None
        return warehouse

    def create(
        self,
        tenant_id: int,
        data: WarehouseCreate,
    ) -> Warehouse:
        # 1. Per-tenant duplicate code check
        existing_code = self.repo.get_by_code(tenant_id, data.code)
        if existing_code:
            raise HTTPException(
                status_code=409,
                detail=f"Warehouse code '{data.code}' already exists",
            )

        # 1b. Per-tenant duplicate name check
        if data.name and data.name.strip():
            clean_name = data.name.strip()
            existing_name = (
                self.db.query(Warehouse)
                .filter(
                    Warehouse.tenant_id == tenant_id,
                    func.lower(Warehouse.name) == clean_name.lower(),
                )
                .first()
            )
            if existing_name:
                raise HTTPException(
                    status_code=409,
                    detail=f"Warehouse name '{clean_name}' already exists",
                )

        # 2. Store tenant isolation check
        store_name = None
        if data.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if not store:
                raise HTTPException(
                    status_code=404,
                    detail="Store not found",
                )
            store_name = store.name

        warehouse = Warehouse(
            tenant_id=tenant_id,
            store_id=data.store_id,
            name=data.name,
            code=data.code,
            address=data.address,
            is_active=True,
        )

        try:
            created = self.repo.create(warehouse)
            created.store_name = store_name
            return created

        except IntegrityError as exc:
            error_message = str(exc).lower()
            if "code" in error_message or "unique" in error_message:
                raise HTTPException(
                    status_code=409,
                    detail="Warehouse code already exists",
                )
            raise HTTPException(
                status_code=400,
                detail="Invalid warehouse data",
            )

    def list(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        store_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[Warehouse]:
        query = self.db.query(Warehouse).filter(Warehouse.tenant_id == tenant_id)

        if search:
            search_clean = search.strip()
            query = query.filter(
                (Warehouse.name.ilike(f"%{search_clean}%"))
                | (Warehouse.code.ilike(f"%{search_clean}%"))
            )

        if is_active is not None:
            query = query.filter(Warehouse.is_active == is_active)

        if store_id is not None:
            query = query.filter(Warehouse.store_id == store_id)

        warehouses = (
            query.order_by(Warehouse.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        for w in warehouses:
            self._attach_store_name(w)

        return warehouses

    def get(
        self,
        tenant_id: int,
        warehouse_id: int,
    ) -> Warehouse:
        warehouse = self.repo.get_by_id(
            warehouse_id,
            tenant_id,
        )

        if not warehouse:
            raise NotFoundException(
                "Warehouse not found"
            )

        return self._attach_store_name(warehouse)

    def update(
        self,
        tenant_id: int,
        warehouse_id: int,
        data: WarehouseUpdate,
    ) -> Warehouse:
        warehouse = self.get(
            tenant_id,
            warehouse_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        # 1. Tenant ownership validation for store_id
        if "store_id" in update_data:
            new_store_id = update_data["store_id"]
            if new_store_id is not None:
                store = (
                    self.db.query(Store)
                    .filter(
                        Store.id == new_store_id,
                        Store.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not store:
                    raise HTTPException(
                        status_code=404,
                        detail="Store not found",
                    )

        # 2. Duplicate code check for this tenant
        if "code" in update_data and update_data["code"] is not None:
            new_code = update_data["code"]
            existing = (
                self.db.query(Warehouse)
                .filter(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.code == new_code,
                    Warehouse.id != warehouse_id,
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Warehouse code '{new_code}' already exists",
                )

        # 2b. Duplicate name check for this tenant
        if "name" in update_data and update_data["name"] is not None:
            new_name = update_data["name"].strip()
            existing_name = (
                self.db.query(Warehouse)
                .filter(
                    Warehouse.tenant_id == tenant_id,
                    func.lower(Warehouse.name) == new_name.lower(),
                    Warehouse.id != warehouse_id,
                )
                .first()
            )
            if existing_name:
                raise HTTPException(
                    status_code=409,
                    detail=f"Warehouse name '{new_name}' already exists",
                )

        for field, value in update_data.items():
            setattr(
                warehouse,
                field,
                value,
            )

        try:
            updated = self.repo.update(warehouse)
            return self._attach_store_name(updated)

        except IntegrityError as exc:
            error_message = str(exc).lower()

            if "code" in error_message or "unique" in error_message:
                raise HTTPException(
                    status_code=409,
                    detail="Warehouse code already exists",
                )

            if "store" in error_message:
                raise HTTPException(
                    status_code=404,
                    detail="Store not found",
                )

            raise HTTPException(
                status_code=400,
                detail="Invalid warehouse data",
            )

    def update_status(
        self,
        tenant_id: int,
        warehouse_id: int,
        is_active: bool,
    ) -> Warehouse:
        warehouse = self.get(tenant_id, warehouse_id)
        warehouse.is_active = is_active
        updated = self.repo.update(warehouse)
        return self._attach_store_name(updated)

    def delete(
        self,
        tenant_id: int,
        warehouse_id: int,
    ) -> dict:
        warehouse = self.get(
            tenant_id,
            warehouse_id,
        )

        # If linked to a store, verify if there is active stock
        if warehouse.store_id:
            active_stock_count = (
                self.db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == warehouse.store_id,
                    Inventory.quantity > 0,
                )
                .count()
            )
            if active_stock_count > 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot delete warehouse: {active_stock_count} product(s) have active stock stored here",
                )

        try:
            self.repo.delete(warehouse)

        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Warehouse cannot be deleted because "
                    "it is being used by other records"
                ),
            )

        return {
            "success": True,
            "message": "Warehouse deleted successfully",
            "data": {"id": warehouse_id},
        }

    def get_stock(
        self,
        tenant_id: int,
        warehouse_id: int,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        warehouse = self.get(tenant_id, warehouse_id)

        if not warehouse.store_id:
            return {
                "success": True,
                "warehouse_id": warehouse.id,
                "warehouse_name": warehouse.name,
                "warehouse_code": warehouse.code,
                "store_id": None,
                "total_items": 0,
                "total_quantity": 0,
                "total_stock_value": Decimal("0.00"),
                "page": page,
                "page_size": page_size,
                "data": [],
            }

        query = (
            self.db.query(Inventory, Product, Category.name.label("category_name"))
            .join(Product, Inventory.product_id == Product.id)
            .outerjoin(Category, Product.category_id == Category.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == warehouse.store_id,
            )
        )

        if search:
            search_clean = search.strip()
            query = query.filter(
                (Product.name.ilike(f"%{search_clean}%"))
                | (Product.sku.ilike(f"%{search_clean}%"))
            )

        total_items = query.count()
        rows = (
            query.order_by(Product.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        stock_items = []
        total_qty = Decimal("0.00")
        total_val = Decimal("0.00")

        # Calculate all totals across the warehouse store
        all_inv = (
            self.db.query(Inventory, Product)
            .join(Product, Inventory.product_id == Product.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == warehouse.store_id,
            )
            .all()
        )
        for inv, prod in all_inv:
            qty = inv.quantity or Decimal("0.0000")
            price = (
                prod.cost_price
                if prod.cost_price and prod.cost_price > Decimal("0.00")
                else (prod.price or Decimal("0.00"))
            )
            total_qty += qty
            total_val += qty * price

        for inv, prod, cat_name in rows:
            qty = inv.quantity or Decimal("0.0000")
            price = (
                prod.cost_price
                if prod.cost_price and prod.cost_price > Decimal("0.00")
                else (prod.price or Decimal("0.00"))
            )
            val = qty * price
            stock_items.append(
                {
                    "product_id": prod.id,
                    "product_name": prod.name,
                    "sku": prod.sku,
                    "category_name": cat_name,
                    "quantity": qty,
                    "min_stock_level": inv.min_stock_level,
                    "unit_cost": prod.cost_price,
                    "selling_price": prod.price,
                    "stock_value": val,
                    "is_low_stock": qty <= inv.min_stock_level,
                }
            )

        return {
            "success": True,
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "warehouse_code": warehouse.code,
            "store_id": warehouse.store_id,
            "total_items": total_items,
            "total_quantity": total_qty,
            "total_stock_value": total_val,
            "page": page,
            "page_size": page_size,
            "data": stock_items,
        }

    def get_transfers(
        self,
        tenant_id: int,
        warehouse_id: int,
        limit: int = 50,
    ) -> dict:
        warehouse = self.get(tenant_id, warehouse_id)

        if not warehouse.store_id:
            return {
                "success": True,
                "warehouse_id": warehouse.id,
                "warehouse_name": warehouse.name,
                "total_transfers": 0,
                "data": [],
            }

        from app.models.store_transfer import StoreTransfer

        transfers = (
            self.db.query(StoreTransfer)
            .filter(
                (StoreTransfer.source_store_id == warehouse.store_id)
                | (StoreTransfer.destination_store_id == warehouse.store_id)
            )
            .order_by(StoreTransfer.created_at.desc())
            .limit(limit)
            .all()
        )

        transfer_items = []
        for t in transfers:
            is_outbound = t.source_store_id == warehouse.store_id
            src = self.db.query(Store).filter(Store.id == t.source_store_id).first()
            dst = self.db.query(Store).filter(Store.id == t.destination_store_id).first()

            transfer_items.append(
                {
                    "transfer_id": t.id,
                    "transfer_number": getattr(t, "transfer_number", f"TR-{t.id:06d}"),
                    "transfer_type": "outbound" if is_outbound else "inbound",
                    "source_store_id": t.source_store_id,
                    "source_store_name": src.name if src else None,
                    "destination_store_id": t.destination_store_id,
                    "destination_store_name": dst.name if dst else None,
                    "status": t.status,
                    "item_count": len(t.items) if hasattr(t, "items") and t.items else 0,
                    "created_at": t.created_at,
                }
            )

        return {
            "success": True,
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "total_transfers": len(transfer_items),
            "data": transfer_items,
        }

    def dashboard(
        self,
        tenant_id: int,
    ) -> dict:
        total = self.repo.count(tenant_id)
        active = self.repo.active_count(tenant_id)

        # Calculate stock across warehouses belonging to this tenant
        linked_store_ids = [
            w.store_id
            for w in self.db.query(Warehouse.store_id)
            .filter(
                Warehouse.tenant_id == tenant_id,
                Warehouse.store_id.isnot(None),
            )
            .all()
            if w.store_id is not None
        ]

        total_stock_units = Decimal("0.00")
        total_stock_value = Decimal("0.00")
        total_products_stored = 0

        if linked_store_ids:
            inv_rows = (
                self.db.query(Inventory, Product)
                .join(Product, Inventory.product_id == Product.id)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id.in_(linked_store_ids),
                )
                .all()
            )
            total_products_stored = len(set(inv.product_id for inv, _ in inv_rows))
            for inv, prod in inv_rows:
                qty = inv.quantity or Decimal("0.0000")
                cost = (
                    prod.cost_price
                    if prod.cost_price and prod.cost_price > Decimal("0.00")
                    else (prod.price or Decimal("0.00"))
                )
                total_stock_units += qty
                total_stock_value += qty * cost

        return {
            "total_warehouses": total,
            "active_warehouses": active,
            "inactive_warehouses": total - active,
            "total_stock_units": int(total_stock_units),
            "total_stock_value": total_stock_value,
            "total_products_stored": total_products_stored,
        }