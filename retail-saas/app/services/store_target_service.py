from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
import threading

from fastapi import status
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


_store_locks: dict[int, threading.Lock] = {}
_store_locks_mutex = threading.Lock()


def get_store_lock(store_id: int) -> threading.Lock:
    """
    Returns a per-store mutex to serialize concurrent target mutations.
    """
    with _store_locks_mutex:
        if store_id not in _store_locks:
            _store_locks[store_id] = threading.Lock()
        return _store_locks[store_id]


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

        # Store-scoping check.
        if (
            current_user_store_id is not None
            and current_user_store_id != data.store_id
        ):
            raise ForbiddenException(
                "You do not have permission to create targets for this store"
            )

        with get_store_lock(data.store_id):
            store = (
                db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .with_for_update()
                .first()
            )

            if not store:
                raise NotFoundException(
                    "Store not found or is inactive in your organization"
                )

            # Calculate date boundaries using the selected period.
            # End dates are exclusive: the first instant of the next period.
            start_date = data.start_date
            end_date = data.end_date

            if data.period == "daily":
                start_date = data.start_date.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                end_date = start_date + timedelta(days=1)

            elif data.period == "weekly":
                selected_date = data.start_date.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                start_date = selected_date - timedelta(
                    days=selected_date.weekday()
                )
                end_date = start_date + timedelta(days=7)

            elif data.period == "monthly":
                start_date = data.start_date.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                if start_date.month == 12:
                    end_date = start_date.replace(
                        year=start_date.year + 1,
                        month=1,
                    )
                else:
                    end_date = start_date.replace(
                        month=start_date.month + 1,
                    )

            elif data.period == "quarterly":
                quarter_start_month = (
                    ((data.start_date.month - 1) // 3) * 3
                ) + 1

                start_date = data.start_date.replace(
                    month=quarter_start_month,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                if quarter_start_month == 10:
                    end_date = start_date.replace(
                        year=start_date.year + 1,
                        month=1,
                    )
                else:
                    end_date = start_date.replace(
                        month=quarter_start_month + 3,
                    )

            elif data.period == "yearly":
                start_date = data.start_date.replace(
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                end_date = start_date.replace(
                    year=start_date.year + 1,
                )

            # Validate the calculated date range.
            if end_date <= start_date:
                raise AppException(
                    "End date must be greater than start date",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # Check overlap only for the same target type and period.
            existing_overlap = (
                StoreTargetRepository.get_overlapping_target(
                    db=db,
                    tenant_id=tenant_id,
                    store_id=data.store_id,
                    target_type=data.target_type,
                    period=data.period,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

            if existing_overlap:
                start_str = existing_overlap.start_date.strftime(
                    "%Y-%m-%d"
                )
                end_str = existing_overlap.end_date.strftime(
                    "%Y-%m-%d"
                )
                raise ConflictException(
                    f"An active target for '{data.target_type}' already "
                    f"exists for this store in an overlapping period "
                    f"({start_str} to {end_str})"
                )

            # Save the calculated boundaries, not the submitted boundaries.
            target = StoreTarget(
                store_id=data.store_id,
                target_type=data.target_type,
                target_value=data.target_value,
                period=data.period,
                start_date=start_date,
                end_date=end_date,
                status=data.status or "active",
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
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        current_user_store_id: Optional[int] = None,
    ) -> list[StoreTarget]:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        # Enforce store scoping.
        if current_user_store_id is not None:
            if (
                store_id is not None
                and store_id != current_user_store_id
            ):
                raise ForbiddenException(
                    "You do not have permission to view targets "
                    "for another store"
                )
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
                raise NotFoundException(
                    "Store not found in your organization"
                )

        return StoreTargetRepository.get_all(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            period=period,
            target_type=target_type,
            skip=skip,
            limit=limit,
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

        if (
            current_user_store_id is not None
            and current_user_store_id != target.store_id
        ):
            raise ForbiddenException(
                "You do not have permission to access targets "
                "for this store"
            )

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

        with get_store_lock(target.store_id):
            # Lock the store row during the update.
            store = (
                db.query(Store)
                .filter(
                    Store.id == target.store_id,
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .with_for_update()
                .first()
            )

            if not store:
                raise NotFoundException(
                    "Store not found or is inactive in your organization"
                )

            if (
                current_user_store_id is not None
                and current_user_store_id != target.store_id
            ):
                raise ForbiddenException(
                    "You do not have permission to modify targets "
                    "for this store"
                )

            # Validate the resulting date range.
            new_start = (
                data.start_date
                if data.start_date is not None
                else target.start_date
            )
            new_end = (
                data.end_date
                if data.end_date is not None
                else target.end_date
            )

            if new_end <= new_start:
                raise AppException(
                    "End date must be greater than start date",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # Resolve the effective target type, period and status.
            new_type = (
                data.target_type
                if data.target_type is not None
                else target.target_type
            )
            new_period = (
                data.period
                if data.period is not None
                else target.period
            )
            new_status = (
                data.status
                if data.status is not None
                else target.status
            )

            # Check overlap for active targets only.
            if new_status == "active":
                existing_overlap = (
                    StoreTargetRepository.get_overlapping_target(
                        db=db,
                        tenant_id=tenant_id,
                        store_id=target.store_id,
                        target_type=new_type,
                        period=new_period,
                        start_date=new_start,
                        end_date=new_end,
                        exclude_target_id=target.id,
                    )
                )

                if existing_overlap:
                    start_str = existing_overlap.start_date.strftime(
                        "%Y-%m-%d"
                    )
                    end_str = existing_overlap.end_date.strftime(
                        "%Y-%m-%d"
                    )
                    raise ConflictException(
                        f"An active target for '{new_type}' already "
                        f"exists for this store in an overlapping period "
                        f"({start_str} to {end_str})"
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

        if (
            current_user_store_id is not None
            and current_user_store_id != target.store_id
        ):
            raise ForbiddenException(
                "You do not have permission to delete targets "
                "for this store"
            )

        StoreTargetRepository.delete(
            db=db,
            target=target,
        )

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

        if (
            current_user_store_id is not None
            and current_user_store_id != target.store_id
        ):
            raise ForbiddenException(
                "You do not have permission to access targets "
                "for this store"
            )

        # Use an exclusive end boundary for the progress queries.
        if "order" in target.target_type.lower():
            count_res = (
                db.query(func.count(Sale.id))
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at < target.end_date,
                    func.lower(Sale.payment_status).notin_(
                        ["cancelled", "failed", "refunded"]
                    ),
                )
                .scalar()
            )
            current_value = Decimal(count_res or 0)

        else:
            sum_res = (
                db.query(
                    func.coalesce(func.sum(Sale.total_amount), 0)
                )
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at < target.end_date,
                    func.lower(Sale.payment_status).notin_(
                        ["cancelled", "failed", "refunded"]
                    ),
                )
                .scalar()
            )
            current_value = Decimal(
                str(sum_res or 0)
            ).quantize(Decimal("0.01"))

        target_value = Decimal(
            str(target.target_value)
        ).quantize(Decimal("0.01"))

        achievement_pct = (
            float(round((current_value / target_value) * 100, 2))
            if target_value > 0
            else 0.0
        )

        remaining = max(
            Decimal("0.00"),
            target_value - current_value,
        ).quantize(Decimal("0.01"))

        is_achieved = current_value >= target_value
        now = datetime.utcnow()

        days_remaining = (
            max(0, (target.end_date - now).days)
            if now < target.end_date
            else 0
        )

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

    @staticmethod
    def auto_complete_expired_targets(
        db: Session,
        now: Optional[datetime] = None,
        tenant_id: Optional[int] = None,
        store_id: Optional[int] = None,
    ) -> dict:
        """
        Safely and idempotently transition active targets whose end_date
        has passed to 'completed'.

        Only transitions targets where status == 'active' and
        end_date < now.
        """
        if now is None:
            now = datetime.utcnow()

        query = db.query(StoreTarget).filter(
            StoreTarget.status == "active",
            StoreTarget.end_date < now,
        )

        if store_id is not None:
            query = query.filter(
                StoreTarget.store_id == store_id
            )
        elif tenant_id is not None:
            query = (
                query.join(
                    Store,
                    Store.id == StoreTarget.store_id,
                )
                .filter(Store.tenant_id == tenant_id)
            )

        expired_targets = query.with_for_update().all()

        transitioned_ids = []

        for target in expired_targets:
            target.status = "completed"
            transitioned_ids.append(target.id)

        if transitioned_ids:
            db.commit()

        return {
            "transitioned_count": len(transitioned_ids),
            "target_ids": transitioned_ids,
            "timestamp": now.isoformat(),
        }
