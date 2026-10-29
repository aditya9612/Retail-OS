from datetime import datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from typing import Optional
import threading

from fastapi import status as http_status
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
            start_date = data.start_date
            end_date = data.end_date

            period_clean = data.period.strip().lower() if data.period else None
            if period_clean in ("15_days", "15 days"):
                period_clean = "15_days"

            if period_clean == "daily":
                start_date = data.start_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                end_date = data.start_date.replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean == "weekly":
                # Week runs Monday (weekday 0) through Sunday (weekday 6)
                start_of_week = (
                    data.start_date - timedelta(days=data.start_date.weekday())
                ).replace(hour=0, minute=0, second=0, microsecond=0)
                start_date = start_of_week
                end_date = (start_of_week + timedelta(days=6)).replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean == "15_days":
                start_date = data.start_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                end_date = (start_date + timedelta(days=14)).replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean == "monthly":
                year = data.start_date.year
                month = data.start_date.month
                _, last_day = monthrange(year, month)
                start_date = data.start_date.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                end_date = data.start_date.replace(
                    day=last_day, hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean == "quarterly":
                quarter = (data.start_date.month - 1) // 3 + 1
                start_month = (quarter - 1) * 3 + 1
                end_month = start_month + 2
                _, last_day = monthrange(data.start_date.year, end_month)
                start_date = data.start_date.replace(
                    month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0
                )
                end_date = data.start_date.replace(
                    month=end_month, day=last_day, hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean == "yearly":
                start_date = data.start_date.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
                end_date = data.start_date.replace(
                    month=12, day=31, hour=23, minute=59, second=59, microsecond=0
                )
            elif period_clean != "all":
                raise AppException(
                    "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # Validate date range.
            if end_date <= start_date:
                raise AppException(
                    "End date must be greater than start date",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
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

        # Validate period filter
        if period is not None and period.strip():
            clean_period = period.strip().lower()
            if clean_period in ("15_days", "15 days"):
                clean_period = "15_days"
            if clean_period not in {"all", "daily", "weekly", "15_days", "monthly", "quarterly", "yearly"}:
                raise AppException(
                    "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            period = None if clean_period == "all" else clean_period
        else:
            period = None

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
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
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

        # Query actual progress from both sales and orders excluding cancelled/failed/refunded
        from app.models.order import Order

        if "order" in target.target_type.lower():
            # Count of completed sales/orders
            sale_count = (
                db.query(func.count(Sale.id))
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at <= target.end_date,
                    func.lower(Sale.payment_status).notin_(
                        ["cancelled", "failed", "refunded"]
                    ),
                )
                .scalar()
                or 0
            )
            order_count = (
                db.query(func.count(Order.id))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == target.store_id,
                    Order.created_at >= target.start_date,
                    Order.created_at <= target.end_date,
                    Order.status != "cancelled",
                )
                .scalar()
                or 0
            )
            current_value = Decimal(sale_count + order_count)
        else:
            # Total sales amount from both sales and orders
            sale_sum = (
                db.query(func.coalesce(func.sum(Sale.total_amount), 0))
                .filter(
                    Sale.tenant_id == tenant_id,
                    Sale.store_id == target.store_id,
                    Sale.created_at >= target.start_date,
                    Sale.created_at <= target.end_date,
                    func.lower(Sale.payment_status).notin_(
                        ["cancelled", "failed", "refunded"]
                    ),
                )
                .scalar()
                or 0
            )
            order_sum = (
                db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == target.store_id,
                    Order.created_at >= target.start_date,
                    Order.created_at <= target.end_date,
                    Order.status != "cancelled",
                )
                .scalar()
                or 0
            )
            current_value = (Decimal(str(sale_sum)) + Decimal(str(order_sum))).quantize(Decimal("0.01"))

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
            store_name=target.store_name,
            store_code=target.store_code,
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
    def get_leaderboard(
        db: Session,
        tenant_id: int,
        period: Optional[str] = None,
        target_type: Optional[str] = None,
        current_user_store_id: Optional[int] = None,
    ) -> dict:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        applied_period_filter = None
        if period is not None and period.strip():
            clean_period = period.strip().lower()
            if clean_period in ("15_days", "15 days"):
                clean_period = "15_days"
            if clean_period not in {"all", "daily", "weekly", "15_days", "monthly", "quarterly", "yearly"}:
                raise AppException(
                    "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            applied_period_filter = clean_period
            query_period = None if clean_period == "all" else clean_period
        else:
            query_period = None

        query = (
            db.query(StoreTarget)
            .join(Store, Store.id == StoreTarget.store_id)
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
                StoreTarget.status == "active",
            )
        )

        if current_user_store_id is not None:
            query = query.filter(StoreTarget.store_id == current_user_store_id)

        if query_period is not None:
            query = query.filter(StoreTarget.period == query_period)

        if target_type is not None and target_type.strip():
            query = query.filter(func.lower(StoreTarget.target_type) == target_type.strip().lower())

        targets = query.all()

        items = []
        for target in targets:
            progress = StoreTargetService.get_target_progress(
                db=db,
                tenant_id=tenant_id,
                target_id=target.id,
                current_user_store_id=current_user_store_id,
            )
            store_name = target.store_name or (target.store.name if getattr(target, "store", None) else f"Store {target.store_id}")
            store_code = target.store_code or (target.store.code if getattr(target, "store", None) else None)

            items.append({
                "target_id": target.id,
                "store_id": target.store_id,
                "store_name": store_name,
                "store_code": store_code,
                "target_type": target.target_type,
                "target_value": progress.target_value,
                "current_value": progress.current_value,
                "achievement_percentage": progress.achievement_percentage,
                "remaining_value": progress.remaining_value,
                "period": target.period,
                "is_achieved": progress.is_achieved,
                "status": target.status,
            })

        # Sort by achievement_percentage DESC, then target_value DESC
        items.sort(key=lambda x: (x["achievement_percentage"], x["target_value"]), reverse=True)

        for idx, item in enumerate(items, start=1):
            item["rank"] = idx

        return {
            "total_ranked": len(items),
            "period_filter": applied_period_filter,
            "target_type_filter": target_type,
            "leaderboard": items,
        }

    @staticmethod
    def get_targets_summary(
        db: Session,
        tenant_id: int,
        period: Optional[str] = None,
        current_user_store_id: Optional[int] = None,
    ) -> dict:
        if tenant_id is None:
            raise AppException("Tenant ID is required")

        applied_period = None
        if period is not None and period.strip():
            clean_period = period.strip().lower()
            if clean_period in ("15_days", "15 days"):
                clean_period = "15_days"
            if clean_period not in {"all", "daily", "weekly", "15_days", "monthly", "quarterly", "yearly"}:
                raise AppException(
                    "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly",
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            applied_period = clean_period
            query_period = None if clean_period == "all" else clean_period
        else:
            query_period = None

        query = (
            db.query(StoreTarget)
            .join(Store, Store.id == StoreTarget.store_id)
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
                StoreTarget.status == "active",
            )
        )

        if current_user_store_id is not None:
            query = query.filter(StoreTarget.store_id == current_user_store_id)

        if query_period is not None:
            query = query.filter(StoreTarget.period == query_period)

        targets = query.all()

        total_targets = len(targets)
        distinct_stores = set()
        total_target_value = Decimal("0.00")
        total_current_value = Decimal("0.00")
        achieved_count = 0
        on_track_count = 0
        lagging_count = 0

        for target in targets:
            distinct_stores.add(target.store_id)
            progress = StoreTargetService.get_target_progress(
                db=db,
                tenant_id=tenant_id,
                target_id=target.id,
                current_user_store_id=current_user_store_id,
            )
            total_target_value += progress.target_value
            total_current_value += progress.current_value

            if progress.is_achieved:
                achieved_count += 1
            elif progress.achievement_percentage >= 50.0 and progress.days_remaining > 5:
                on_track_count += 1
            else:
                lagging_count += 1

        overall_pct = (
            float(round((total_current_value / total_target_value) * 100, 2))
            if total_target_value > 0
            else 0.0
        )

        return {
            "total_targets": total_targets,
            "total_stores_with_targets": len(distinct_stores),
            "total_target_value": total_target_value,
            "total_current_value": total_current_value,
            "overall_achievement_percentage": overall_pct,
            "achieved_targets_count": achieved_count,
            "on_track_targets_count": on_track_count,
            "lagging_targets_count": lagging_count,
            "period": applied_period,
        }

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
