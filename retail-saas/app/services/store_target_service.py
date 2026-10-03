from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.sale import Sale
from app.models.store import Store
from app.models.store_target import StoreTarget
from app.repositories.store_target_repo import StoreTargetRepository
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetProgressResponse,
    StoreTargetUpdate,
)


class StoreTargetService:

    @staticmethod
    def create_target(
        db: Session,
        tenant_id: int,
        data: StoreTargetCreate,
        current_user_store_id: Optional[int] = None,
    ) -> StoreTarget:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        # Store-scoping check
        if current_user_store_id is not None and current_user_store_id != data.store_id:
            raise ForbiddenException("You do not have permission to create targets for this store")

        store = (
            db.query(Store)
            .filter(
                Store.id == data.store_id,
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )

        if not store:
            raise NotFoundException("Store not found or is inactive in your organization")

        # Date validation
        if data.end_date <= data.start_date:
            raise AppException("End date must be greater than start date")

        # Overlapping target check
        existing_overlap = StoreTargetRepository.get_overlapping_target(
            db=db,
            tenant_id=tenant_id,
            store_id=data.store_id,
            target_type=data.target_type,
            start_date=data.start_date,
            end_date=data.end_date,
        )
        if existing_overlap:
            start_str = existing_overlap.start_date.strftime("%Y-%m-%d")
            end_str = existing_overlap.end_date.strftime("%Y-%m-%d")
            raise ConflictException(
                f"An active target for '{data.target_type}' already exists for this store in an overlapping period ({start_str} to {end_str})"
            )

        target = StoreTarget(
            store_id=data.store_id,
            target_type=data.target_type,
            target_value=data.target_value,
            period=data.period,
            start_date=data.start_date,
            end_date=data.end_date,
            status="active",
        )

        return StoreTargetRepository.create(
            db=db,
            target=target,
        )

    @staticmethod
    def get_targets(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        period: Optional[str] = None,
        target_type: Optional[str] = None,
        current_user_store_id: Optional[int] = None,
    ) -> list[StoreTarget]:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        # Enforce store scoping
        if current_user_store_id is not None:
            if store_id is not None and store_id != current_user_store_id:
                raise ForbiddenException("You do not have permission to view targets for another store")
            store_id = current_user_store_id

        if store_id is not None:
            store = (
                db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if not store:
                raise NotFoundException("Store not found in your organization")

        return StoreTargetRepository.get_all(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            period=period,
            target_type=target_type,
        )

    @staticmethod
    def get_target(
        db: Session,
        tenant_id: int,
        target_id: int,
        current_user_store_id: Optional[int] = None,
    ) -> StoreTarget:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        target = StoreTargetRepository.get_by_id_and_tenant(
            db=db,
            target_id=target_id,
            tenant_id=tenant_id,
        )

        if not target:
            raise NotFoundException("Store target not found")

        if current_user_store_id is not None and current_user_store_id != target.store_id:
            raise ForbiddenException("You do not have permission to access targets for this store")

        return target

    @staticmethod
    def update_target(
        db: Session,
        tenant_id: int,
        target_id: int,
        data: StoreTargetUpdate,
        current_user_store_id: Optional[int] = None,
    ) -> StoreTarget:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        target = StoreTargetRepository.get_by_id_and_tenant(
            db=db,
            target_id=target_id,
            tenant_id=tenant_id,
        )

        if not target:
            raise NotFoundException("Store target not found")

        if current_user_store_id is not None and current_user_store_id != target.store_id:
            raise ForbiddenException("You do not have permission to modify targets for this store")

        # Validate resulting date range
        new_start = data.start_date if data.start_date is not None else target.start_date
        new_end = data.end_date if data.end_date is not None else target.end_date
        if new_end <= new_start:
            raise AppException("End date must be greater than start date")

        # Validate overlap if dates, type, or status are changed
        new_type = data.target_type if data.target_type is not None else target.target_type
        new_status = data.status if data.status is not None else target.status

        if new_status == "active":
            existing_overlap = StoreTargetRepository.get_overlapping_target(
                db=db,
                tenant_id=tenant_id,
                store_id=target.store_id,
                target_type=new_type,
                start_date=new_start,
                end_date=new_end,
                exclude_target_id=target.id,
            )
            if existing_overlap:
                start_str = existing_overlap.start_date.strftime("%Y-%m-%d")
                end_str = existing_overlap.end_date.strftime("%Y-%m-%d")
                raise ConflictException(
                    f"An active target for '{new_type}' already exists for this store in an overlapping period ({start_str} to {end_str})"
                )

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(target, key, value)

        return StoreTargetRepository.update(
            db=db,
            target=target,
        )

    @staticmethod
    def delete_target(
        db: Session,
        tenant_id: int,
        target_id: int,
        current_user_store_id: Optional[int] = None,
    ) -> None:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        target = StoreTargetRepository.get_by_id_and_tenant(
            db=db,
            target_id=target_id,
            tenant_id=tenant_id,
        )

        if not target:
            raise NotFoundException("Store target not found")

        if current_user_store_id is not None and current_user_store_id != target.store_id:
            raise ForbiddenException("You do not have permission to delete targets for this store")

        StoreTargetRepository.delete(db=db, target=target)

    @staticmethod
    def get_target_progress(
        db: Session,
        tenant_id: int,
        target_id: int,
        current_user_store_id: Optional[int] = None,
    ) -> StoreTargetProgressResponse:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        target = StoreTargetRepository.get_by_id_and_tenant(
            db=db,
            target_id=target_id,
            tenant_id=tenant_id,
        )

        if not target:
            raise NotFoundException("Store target not found")

        if current_user_store_id is not None and current_user_store_id != target.store_id:
            raise ForbiddenException("You do not have permission to access targets for this store")

        # Query actual progress from sales
        if "order" in target.target_type.lower():
            # Count of completed sales/orders
            count_res = (
                db.query(func.count(Sale.id))
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at <= target.end_date,
                )
                .scalar()
            )
            current_value = Decimal(count_res or 0)
        else:
            # Total sales amount
            sum_res = (
                db.query(func.coalesce(func.sum(Sale.total_amount), 0))
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at <= target.end_date,
                )
                .scalar()
            )
            current_value = Decimal(str(sum_res or 0)).quantize(Decimal("0.01"))

        target_value = Decimal(str(target.target_value)).quantize(Decimal("0.01"))
        achievement_pct = (
            float(round((current_value / target_value) * 100, 2))
            if target_value > 0
            else 0.0
        )
        remaining = max(Decimal("0.00"), target_value - current_value).quantize(Decimal("0.01"))
        is_achieved = current_value >= target_value
        now = datetime.utcnow()
        days_remaining = max(0, (target.end_date - now).days) if now < target.end_date else 0

        return StoreTargetProgressResponse(
            id=target.id,
            store_id=target.store_id,
            target_type=target.target_type,
            target_value=target_value,
            current_value=current_value,
            achievement_percentage=achievement_pct,
            remaining_value=remaining,
            period=target.period,
            start_date=target.start_date,
            end_date=target.end_date,
            status=target.status,
            is_achieved=is_achieved,
            days_remaining=days_remaining,
        )
        )