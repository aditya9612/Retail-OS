from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import NotFoundException
from app.models.warehouse import Warehouse
from app.repositories.warehouse_repo import WarehouseRepository
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseUpdate,
)


class WarehouseService:

    def __init__(self, db):
        self.repo = WarehouseRepository(db)

    def create(
        self,
        tenant_id: int,
        data: WarehouseCreate,
    ):
        warehouse = Warehouse(
            tenant_id=tenant_id,
            store_id=data.store_id,
            name=data.name,
            code=data.code,
            address=data.address,
            is_active=True,
        )

        try:
            return self.repo.create(warehouse)

        except IntegrityError as exc:
            error_message = str(exc).lower()

            if "code" in error_message:
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

    def list(
        self,
        tenant_id: int,
    ):
        return self.repo.list(tenant_id)

    def get(
        self,
        tenant_id: int,
        warehouse_id: int,
    ):
        warehouse = self.repo.get_by_id(
            warehouse_id,
            tenant_id,
        )

        if not warehouse:
            raise NotFoundException(
                "Warehouse not found"
            )

        return warehouse

    def update(
        self,
        tenant_id: int,
        warehouse_id: int,
        data: WarehouseUpdate,
    ):
        warehouse = self.get(
            tenant_id,
            warehouse_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        for field, value in update_data.items():
            setattr(
                warehouse,
                field,
                value,
            )

        try:
            return self.repo.update(warehouse)

        except IntegrityError as exc:
            error_message = str(exc).lower()

            if "code" in error_message:
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

    def delete(
        self,
        tenant_id: int,
        warehouse_id: int,
    ):
        warehouse = self.get(
            tenant_id,
            warehouse_id,
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
            "message": "Warehouse deleted successfully"
        }

    
    def dashboard(
        self,
        tenant_id: int,
    ):
        total = self.repo.count(tenant_id)
        active = self.repo.active_count(tenant_id)

        return {
            "total_warehouses": total,
            "active_warehouses": active,
            "inactive_warehouses": total - active,
        }