import math
import re
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    create_super_admin_access_token,
    create_super_admin_refresh_token,
    get_password_hash,
    verify_password,
)
from decimal import Decimal
from app.models.role import Role
from app.models.saas_billing import SaaSInvoice, SaaSPlan, SaaSSubscription, SaaSUPITransaction
from app.models.store import Store
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.schemas.saas_entitlement import (
    SaaSPlanEntitlementCreate,
    SaaSPlanEntitlementUpdate,
)
from app.schemas.saas_invoice import SaaSInvoiceResponse
from app.schemas.saas_plan import (
    SaaSPlanCreate,
    SaaSPlanUpdate,
)
from app.schemas.saas_upi import UPITransactionResponse
from app.schemas.super_admin import (
    SuperAdminChangePassword,
    SuperAdminCreate,
    SuperAdminEntitlementUsage,
    SuperAdminInvoiceListItem,
    SuperAdminLogin,
    SuperAdminPlanSummary,
    SuperAdminStoreOwnerCreate,
    SuperAdminStoreOwnerUpdate,
    SuperAdminSubscriptionDetailInfo,
    SuperAdminSubscriptionListItem,
    SuperAdminTenantSummary,
    SuperAdminUpdate,
)
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.services.saas_subscription_service import SaaSSubscriptionService
from app.utils.constants import DEFAULT_ROLE_PERMISSIONS, UserRole


class SuperAdminService:

    def __init__(self, db: Session):
        self.db = db

    def create_super_admin(
        self,
        data: SuperAdminCreate,
    ) -> SuperAdmin:
        count = self.db.query(SuperAdmin).count()
        if count >= 1:
            raise ConflictException(
                "Only ONE Super Admin is permitted in the system"
            )

        existing = (
            self.db.query(SuperAdmin)
            .filter(
                func.lower(SuperAdmin.email)
                == data.email.lower()
            )
            .first()
        )

        if existing:
            raise ConflictException(
                "SuperAdmin with this email already exists"
            )

        super_admin = SuperAdmin(
            email=data.email,
            full_name=data.full_name,
            hashed_password=get_password_hash(
                data.password
            ),
            phone=data.phone,
            is_active=True,
        )

        self.db.add(super_admin)
        self.db.commit()
        self.db.refresh(super_admin)

        return super_admin

    def login(
        self,
        data: SuperAdminLogin,
    ):
        super_admin = (
            self.db.query(SuperAdmin)
            .filter(
                func.lower(SuperAdmin.email)
                == data.email.lower()
            )
            .first()
        )

        if not super_admin:
            raise UnauthorizedException(
                "Invalid email or password"
            )

        if not verify_password(
            data.password,
            super_admin.hashed_password,
        ):
            raise UnauthorizedException(
                "Invalid email or password"
            )

        if not super_admin.is_active:
            raise UnauthorizedException(
                "Super Admin account is disabled"
            )

        token_data = {
            "sub": str(super_admin.id),
            "role": "SUPERADMIN",
        }

        return {
            "access_token": create_super_admin_access_token(
                token_data
            ),
            "refresh_token": create_super_admin_refresh_token(
                token_data
            ),
            "token_type": "bearer",
        }

    def get_by_id(
        self,
        super_admin_id: int,
    ) -> SuperAdmin:
        super_admin = (
            self.db.query(SuperAdmin)
            .filter(
                SuperAdmin.id == super_admin_id
            )
            .first()
        )

        if not super_admin:
            raise NotFoundException(
                "Super Admin not found"
            )

        return super_admin

    def list_super_admins(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> dict:
        query = self.db.query(SuperAdmin)

        if is_active is not None:
            query = query.filter(SuperAdmin.is_active.is_(is_active))

        if search:
            clean_search = search.strip()
            if clean_search:
                term = f"%{clean_search}%"
                query = query.filter(
                    or_(
                        SuperAdmin.full_name.ilike(term),
                        SuperAdmin.email.ilike(term),
                        SuperAdmin.phone.ilike(term),
                    )
                )

        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if total == 0:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
            }

        skip = (page - 1) * page_size
        items = (
            query
            .order_by(SuperAdmin.created_at.desc(), SuperAdmin.id.desc())
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def update_super_admin(
        self,
        super_admin_id: int,
        data: SuperAdminUpdate,
    ) -> SuperAdmin:
        super_admin = self.get_by_id(
            super_admin_id
        )

        if data.email is not None:
            existing = (
                self.db.query(SuperAdmin)
                .filter(
                    func.lower(SuperAdmin.email)
                    == data.email.lower(),
                    SuperAdmin.id != super_admin_id,
                )
                .first()
            )

            if existing:
                raise ConflictException(
                    "Email already belongs to another Super Admin"
                )

            super_admin.email = data.email

        if data.full_name is not None:
            super_admin.full_name = data.full_name

        if data.phone is not None:
            super_admin.phone = data.phone

        self.db.commit()
        self.db.refresh(super_admin)

        return super_admin

    def update_status(
        self,
        super_admin_id: int,
        is_active: bool,
    ) -> SuperAdmin:
        super_admin = self.get_by_id(
            super_admin_id
        )

        super_admin.is_active = is_active

        self.db.commit()
        self.db.refresh(super_admin)

        return super_admin

    def delete_super_admin(
        self,
        super_admin_id: int,
        current_super_admin_id: int,
    ):
        super_admin = self.get_by_id(
            super_admin_id
        )

        if super_admin.id == current_super_admin_id:
            raise ConflictException(
                "You cannot delete your own Super Admin account"
            )

        self.db.delete(super_admin)
        self.db.commit()

        return {
            "success": True,
            "message": "Super Admin deleted successfully",
        }

    def change_password(
        self,
        super_admin_id: int,
        data: SuperAdminChangePassword,
    ):
        super_admin = self.get_by_id(
            super_admin_id
        )

        if not verify_password(
            data.current_password,
            super_admin.hashed_password,
        ):
            raise UnauthorizedException(
                "Current password is incorrect"
            )

        super_admin.hashed_password = get_password_hash(
            data.new_password
        )

        self.db.commit()

        return {
            "success": True,
            "message": "Password changed successfully",
        }

    def list_tenants(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        plan: str | None = None,
        subscription_status: str | None = None,
    ) -> dict:
        query = self.db.query(Tenant)

        if is_active is not None:
            query = query.filter(Tenant.is_active.is_(is_active))

        if plan:
            clean_plan = plan.strip()
            if clean_plan:
                query = query.filter(Tenant.plan == clean_plan)

        if subscription_status:
            clean_status = subscription_status.strip()
            if clean_status:
                query = query.filter(Tenant.subscription_status == clean_status)

        if search:
            clean_search = search.strip()
            if clean_search:
                term = f"%{clean_search}%"
                query = query.filter(
                    or_(
                        Tenant.name.ilike(term),
                        Tenant.domain.ilike(term),
                        Tenant.users.any(User.email.ilike(term)),
                    )
                )

        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if total == 0:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
            }

        skip = (page - 1) * page_size
        items = (
            query
            .order_by(Tenant.created_at.desc(), Tenant.id.desc())
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_tenant(
        self,
        tenant_id: int,
    ) -> dict:
        tenant = (
            self.db.query(Tenant)
            .filter(
                Tenant.id == tenant_id
            )
            .first()
        )

        if not tenant:
            raise NotFoundException(
                "Tenant not found"
            )

        # 1. Store counts via DB-level aggregation
        store_stats = (
            self.db.query(
                func.count(Store.id).label("total"),
                func.coalesce(
                    func.sum(case((Store.is_active.is_(True), 1), else_=0)),
                    0,
                ).label("active"),
            )
            .filter(Store.tenant_id == tenant_id)
            .one()
        )
        total_stores = store_stats.total or 0
        active_stores = int(store_stats.active or 0)

        # 2. User / Staff counts via DB-level aggregation
        user_stats = (
            self.db.query(
                func.count(User.id).label("total"),
                func.coalesce(
                    func.sum(case((User.is_active.is_(True), 1), else_=0)),
                    0,
                ).label("active"),
            )
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
            .one()
        )
        total_users = user_stats.total or 0
        active_users = int(user_stats.active or 0)

        # 3. Owner / Admin info
        owner_user = (
            self.db.query(User)
            .join(Role, Role.id == User.role_id)
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
                func.lower(Role.name).in_(["admin", "owner"]),
            )
            .order_by(User.id.asc())
            .first()
        )

        if not owner_user:
            owner_user = (
                self.db.query(User)
                .filter(
                    User.tenant_id == tenant_id,
                    User.is_deleted.is_(False),
                )
                .order_by(User.id.asc())
                .first()
            )

        owner_data = None
        if owner_user:
            role_name = owner_user.role.name if owner_user.role else None
            owner_data = {
                "id": owner_user.id,
                "email": owner_user.email,
                "full_name": owner_user.full_name,
                "phone": owner_user.phone,
                "role": role_name,
                "is_active": owner_user.is_active,
                "created_at": owner_user.created_at,
            }

        # 4. Concise store summary list (deterministic ordering, limit 20)
        store_records = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id)
            .order_by(Store.is_main.desc(), Store.id.asc())
            .limit(20)
            .all()
        )

        stores_summary = [
            {
                "id": s.id,
                "name": s.name,
                "code": s.code,
                "city": s.city,
                "state": s.state,
                "is_main": s.is_main,
                "is_active": s.is_active,
                "created_at": s.created_at,
            }
            for s in store_records
        ]

        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "email": tenant.email,
            "phone": tenant.phone,
            "is_active": tenant.is_active,
            "plan": tenant.plan,
            "subscription_status": tenant.subscription_status,
            "subscription_end_date": tenant.subscription_end_date,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
            "owner": owner_data,
            "total_stores": total_stores,
            "active_stores": active_stores,
            "total_users": total_users,
            "active_users": active_users,
            "stores": stores_summary,
        }

    def create_tenant(
        self,
        data: SuperAdminStoreOwnerCreate,
    ) -> dict:
        store_name = (data.store_name or data.tenant_name or "").strip()
        owner_name = (data.owner_name or data.admin_name or "").strip()
        owner_email = str(data.owner_email or data.email or "").strip().lower()
        owner_phone = data.owner_phone or data.phone
        domain_val = (data.domain or data.slug or "").strip().lower()

        if not store_name:
            raise AppException("Store name is required")
        if not owner_name:
            raise AppException("Owner name is required")
        if not owner_email:
            raise AppException("Owner email is required")

        if not domain_val:
            base_slug = re.sub(r"[^a-z0-9]+", "-", store_name.lower()).strip("-")
            domain_val = base_slug or "store"

        domain_val = re.sub(r"[^a-z0-9-]+", "", domain_val).strip("-")
        if not domain_val:
            domain_val = "store"

        candidate_domain = domain_val
        counter = 1
        while self.db.query(Tenant).filter(Tenant.domain == candidate_domain).first():
            candidate_domain = f"{domain_val}-{counter}"
            counter += 1
        domain_val = candidate_domain

        existing_user = (
            self.db.query(User)
            .filter(func.lower(User.email) == owner_email.lower())
            .first()
        )
        if existing_user:
            raise ConflictException("Email address is already registered")

        try:
            settings_dict = {}
            if data.address:
                settings_dict["address"] = data.address
            if data.city:
                settings_dict["city"] = data.city
            if data.state:
                settings_dict["state"] = data.state
            if data.pincode:
                settings_dict["pincode"] = data.pincode
            if owner_phone:
                settings_dict["phone"] = owner_phone
            if owner_email:
                settings_dict["email"] = owner_email

            tenant = Tenant(
                name=store_name,
                domain=domain_val,
                is_active=True,
                settings=settings_dict or None,
            )
            self.db.add(tenant)
            self.db.flush()

            for role_name in UserRole:
                if role_name == UserRole.SUPERADMIN:
                    continue
                role = Role(
                    tenant_id=tenant.id,
                    name=role_name.value,
                    permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
                    is_system=False,
                )
                self.db.add(role)
            self.db.flush()

            admin_role = (
                self.db.query(Role)
                .filter(
                    Role.tenant_id == tenant.id,
                    Role.name == UserRole.ADMIN.value,
                )
                .first()
            )
            if not admin_role:
                self.db.rollback()
                raise AppException("Admin role could not be created")

            main_store = Store(
                tenant_id=tenant.id,
                name=store_name,
                code="MAIN-01",
                address=data.address,
                city=data.city,
                state=data.state,
                pincode=data.pincode,
                phone=owner_phone,
                email=owner_email,
                is_main=True,
                is_active=True,
            )
            self.db.add(main_store)
            self.db.flush()

            user = User(
                tenant_id=tenant.id,
                role_id=admin_role.id,
                store_id=None,
                email=owner_email,
                password_hash=get_password_hash(data.password),
                full_name=owner_name,
                phone=owner_phone,
                is_active=True,
            )
            self.db.add(user)
            self.db.flush()

            SaaSSubscriptionService(self.db).create_initial_subscription(
                tenant_id=tenant.id,
                plan_id=data.plan_id,
                plan_code=data.plan_code,
            )

            self.db.commit()
            return self.get_tenant(tenant.id)
        except ConflictException:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictException("Tenant or user information already exists") from exc
        except Exception:
            self.db.rollback()
            raise

    def update_tenant(
        self,
        tenant_id: int,
        data: SuperAdminStoreOwnerUpdate,
    ) -> dict:
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise NotFoundException("Tenant not found")

        store_name = data.store_name or data.tenant_name
        if store_name is not None and store_name.strip():
            tenant.name = store_name.strip()

        if data.is_active is not None:
            tenant.is_active = data.is_active

        settings = dict(tenant.settings or {})
        if data.address is not None:
            settings["address"] = data.address
        if data.city is not None:
            settings["city"] = data.city
        if data.state is not None:
            settings["state"] = data.state
        if data.pincode is not None:
            settings["pincode"] = data.pincode
        owner_phone = data.owner_phone or data.phone
        if owner_phone is not None:
            settings["phone"] = owner_phone
        tenant.settings = settings

        owner_name = data.owner_name or data.admin_name
        if owner_name is not None or owner_phone is not None:
            owner_user = (
                self.db.query(User)
                .join(Role, Role.id == User.role_id)
                .filter(
                    User.tenant_id == tenant_id,
                    User.is_deleted.is_(False),
                    func.lower(Role.name).in_(["admin", "owner"]),
                )
                .order_by(User.id.asc())
                .first()
            )
            if owner_user:
                if owner_name is not None:
                    owner_user.full_name = owner_name.strip()
                if owner_phone is not None:
                    owner_user.phone = owner_phone.strip()

        self.db.commit()
        return self.get_tenant(tenant.id)

    def delete_tenant(
        self,
        tenant_id: int,
    ) -> dict:
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise NotFoundException("Tenant not found")

        tenant.is_active = False

        stores = self.db.query(Store).filter(Store.tenant_id == tenant_id).all()
        for s in stores:
            s.is_active = False

        users = self.db.query(User).filter(User.tenant_id == tenant_id).all()
        for u in users:
            u.is_active = False
            u.is_deleted = True

        self.db.commit()
        return {
            "success": True,
            "message": f"Store Owner (Tenant {tenant_id}) deleted/deactivated successfully",
        }

    def update_tenant_status(
        self,
        tenant_id: int,
        is_active: bool,
    ) -> Tenant:
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        if not tenant:
            raise NotFoundException("Tenant not found")

        tenant.is_active = is_active

        self.db.commit()
        self.db.refresh(tenant)

        return tenant

    def list_tenant_users(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> dict:
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        if not tenant:
            raise NotFoundException("Tenant not found")

        query = (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
        )

        if is_active is not None:
            query = query.filter(User.is_active.is_(is_active))

        if role:
            clean_role = role.strip()
            if clean_role:
                query = query.join(Role, Role.id == User.role_id).filter(
                    func.lower(Role.name) == clean_role.lower()
                )

        if search:
            clean_search = search.strip()
            if clean_search:
                term = f"%{clean_search}%"
                query = query.filter(
                    or_(
                        User.full_name.ilike(term),
                        User.email.ilike(term),
                        User.phone.ilike(term),
                    )
                )

        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if total == 0:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
            }

        skip = (page - 1) * page_size
        items = (
            query
            .options(joinedload(User.role))
            .order_by(User.created_at.desc(), User.id.desc())
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def list_tenant_stores(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        is_main: bool | None = None,
        city: str | None = None,
        state: str | None = None,
    ) -> dict:
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        if not tenant:
            raise NotFoundException("Tenant not found")

        query = self.db.query(Store).filter(Store.tenant_id == tenant_id)

        if is_active is not None:
            query = query.filter(Store.is_active.is_(is_active))

        if is_main is not None:
            query = query.filter(Store.is_main.is_(is_main))

        if city:
            clean_city = city.strip()
            if clean_city:
                query = query.filter(func.lower(Store.city) == clean_city.lower())

        if state:
            clean_state = state.strip()
            if clean_state:
                query = query.filter(func.lower(Store.state) == clean_state.lower())

        if search:
            clean_search = search.strip()
            if clean_search:
                term = f"%{clean_search}%"
                query = query.filter(
                    or_(
                        Store.name.ilike(term),
                        Store.code.ilike(term),
                        Store.city.ilike(term),
                        Store.phone.ilike(term),
                        Store.email.ilike(term),
                    )
                )

        total = query.count()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if total == 0:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
            }

        skip = (page - 1) * page_size
        items = (
            query
            .order_by(Store.created_at.desc(), Store.id.desc())
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def dashboard(self):
        total_super_admins = (
            self.db.query(SuperAdmin)
            .count()
        )

        active_super_admins = (
            self.db.query(SuperAdmin)
            .filter(
                SuperAdmin.is_active.is_(True)
            )
            .count()
        )

        inactive_super_admins = (
            self.db.query(SuperAdmin)
            .filter(
                SuperAdmin.is_active.is_(False)
            )
            .count()
        )

        total_tenants = (
            self.db.query(Tenant)
            .count()
        )

        total_users = (
            self.db.query(User)
            .count()
        )

        active_tenants = 0
        inactive_tenants = 0

        if hasattr(Tenant, "is_active"):
            active_tenants = (
                self.db.query(Tenant)
                .filter(
                    Tenant.is_active.is_(True)
                )
                .count()
            )

            inactive_tenants = (
                self.db.query(Tenant)
                .filter(
                    Tenant.is_active.is_(False)
                )
                .count()
            )

        # Subscription status breakdown
        valid_statuses = ["trialing", "active", "past_due", "expired", "cancelled"]
        subscriptions_by_status = {st: 0 for st in valid_statuses}
        status_counts = (
            self.db.query(SaaSSubscription.status, func.count(SaaSSubscription.id))
            .group_by(SaaSSubscription.status)
            .all()
        )
        for st, count in status_counts:
            subscriptions_by_status[st] = count

        expired_subscriptions_count = subscriptions_by_status.get("expired", 0)

        pending_upgrades_count = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.pending_plan_id.isnot(None))
            .count()
        )

        scheduled_downgrades_count = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.scheduled_plan_id.isnot(None))
            .count()
        )

        # Cumulative paid SaaS invoice revenue
        total_rev = (
            self.db.query(func.coalesce(func.sum(SaaSInvoice.total_amount), 0))
            .filter(SaaSInvoice.status == "paid")
            .scalar()
        )
        total_saas_revenue = Decimal(str(total_rev)) if total_rev is not None else Decimal("0.00")

        return {
            "total_super_admins": total_super_admins,
            "active_super_admins": active_super_admins,
            "inactive_super_admins": inactive_super_admins,
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "inactive_tenants": inactive_tenants,
            "total_users": total_users,
            "subscriptions_by_status": subscriptions_by_status,
            "expired_subscriptions_count": expired_subscriptions_count,
            "pending_upgrades_count": pending_upgrades_count,
            "scheduled_downgrades_count": scheduled_downgrades_count,
            "total_saas_revenue": total_saas_revenue,
        }

    # =========================
    # SAAS PLAN CATALOG CRUD
    # =========================

    def create_plan(
        self,
        data: SaaSPlanCreate,
    ) -> SaaSPlan:
        code_norm = data.code.strip().lower()

        existing = (
            self.db.query(SaaSPlan)
            .filter(
                func.lower(SaaSPlan.code) == code_norm
            )
            .first()
        )

        if existing:
            raise ConflictException(
                f"Plan with code '{data.code}' already exists"
            )

        plan = SaaSPlan(
            name=data.name.strip(),
            code=code_norm,
            description=data.description.strip() if data.description is not None else None,
            price=data.price,
            currency=data.currency,
            billing_interval=data.billing_interval,
            trial_days=data.trial_days,
            is_active=data.is_active,
        )

        try:
            self.db.add(plan)
            self.db.commit()
            self.db.refresh(plan)
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(
                f"Plan with code '{data.code}' already exists"
            )

        return plan

    def list_plans(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> dict:
        query = self.db.query(SaaSPlan)

        if is_active is not None:
            query = query.filter(
                SaaSPlan.is_active.is_(is_active)
            )

        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    SaaSPlan.name.ilike(search_term),
                    SaaSPlan.code.ilike(search_term),
                )
            )

        total = query.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        skip = (page - 1) * page_size

        items = (
            query
            .order_by(
                SaaSPlan.created_at.desc(),
                SaaSPlan.id.desc(),
            )
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_plan(
        self,
        plan_id: int,
    ) -> SaaSPlan:
        plan = (
            self.db.query(SaaSPlan)
            .filter(SaaSPlan.id == plan_id)
            .first()
        )

        if not plan:
            raise NotFoundException(
                "SaaS Plan not found"
            )

        return plan

    def update_plan(
        self,
        plan_id: int,
        data: SaaSPlanUpdate,
    ) -> SaaSPlan:
        plan = self.get_plan(plan_id)

        update_dict = data.model_dump(
            exclude_unset=True
        )

        # Protect immutable and system managed fields
        update_dict.pop("id", None)
        update_dict.pop("code", None)
        update_dict.pop("created_at", None)
        update_dict.pop("updated_at", None)

        for key, value in update_dict.items():
            if key == "description" and value is not None:
                value = value.strip()
            elif key == "name" and value is not None:
                value = value.strip()
            setattr(plan, key, value)

        self.db.commit()
        self.db.refresh(plan)

        return plan

    def activate_plan(
        self,
        plan_id: int,
    ) -> SaaSPlan:
        plan = self.get_plan(plan_id)
        plan.is_active = True
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def deactivate_plan(
        self,
        plan_id: int,
    ) -> SaaSPlan:
        plan = self.get_plan(plan_id)
        plan.is_active = False
        self.db.commit()
        self.db.refresh(plan)
        return plan

    # =========================
    # SAAS PLAN ENTITLEMENTS
    # =========================

    def list_plan_entitlements(
        self,
        plan_id: int,
    ) -> dict:
        plan = self.get_plan(plan_id)
        items = (
            self.db.query(SaaSPlanEntitlement)
            .filter(SaaSPlanEntitlement.plan_id == plan.id)
            .order_by(SaaSPlanEntitlement.id.asc())
            .all()
        )
        return {
            "plan_id": plan.id,
            "items": items,
            "total": len(items),
        }

    def create_plan_entitlement(
        self,
        plan_id: int,
        data: SaaSPlanEntitlementCreate,
    ) -> SaaSPlanEntitlement:
        plan = self.get_plan(plan_id)
        dim = data.dimension.strip().lower()

        if dim not in EntitlementDimension.ALL:
            raise AppException(
                f"Invalid entitlement dimension '{data.dimension}'. Allowed: {sorted(list(EntitlementDimension.ALL))}"
            )

        existing = (
            self.db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == plan.id,
                SaaSPlanEntitlement.dimension == dim,
            )
            .first()
        )
        if existing:
            raise ConflictException(
                f"Entitlement for dimension '{dim}' already exists on plan {plan.id}"
            )

        if data.is_unlimited:
            val = None
        else:
            if data.value is None or data.value < 0:
                raise AppException("Limited entitlement must specify a non-negative value")
            val = data.value

        entitlement = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=dim,
            value=val,
            is_unlimited=data.is_unlimited,
        )

        try:
            self.db.add(entitlement)
            self.db.flush()
            self.db.commit()
            self.db.refresh(entitlement)
            return entitlement
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(
                f"Entitlement for dimension '{dim}' already exists on plan {plan.id}"
            )

    def update_plan_entitlement(
        self,
        plan_id: int,
        dimension: str,
        data: SaaSPlanEntitlementUpdate,
    ) -> SaaSPlanEntitlement:
        plan = self.get_plan(plan_id)
        dim = dimension.strip().lower()

        if dim not in EntitlementDimension.ALL:
            raise AppException(
                f"Invalid entitlement dimension '{dimension}'. Allowed: {sorted(list(EntitlementDimension.ALL))}"
            )

        entitlement = (
            self.db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == plan.id,
                SaaSPlanEntitlement.dimension == dim,
            )
            .first()
        )
        if not entitlement:
            raise NotFoundException(
                f"Entitlement for dimension '{dim}' not found on plan {plan.id}"
            )

        if data.is_unlimited:
            entitlement.is_unlimited = True
            entitlement.value = None
        else:
            if data.value is None or data.value < 0:
                raise AppException("Limited entitlement must specify a non-negative value")
            entitlement.is_unlimited = False
            entitlement.value = data.value

        try:
            self.db.flush()
            self.db.commit()
            self.db.refresh(entitlement)
            return entitlement
        except Exception:
            self.db.rollback()
            raise

    def delete_plan_entitlement(
        self,
        plan_id: int,
        dimension: str,
    ) -> None:
        plan = self.get_plan(plan_id)
        dim = dimension.strip().lower()

        entitlement = (
            self.db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == plan.id,
                SaaSPlanEntitlement.dimension == dim,
            )
            .first()
        )
        if not entitlement:
            raise NotFoundException(
                f"Entitlement for dimension '{dim}' not found on plan {plan.id}"
            )

        try:
            self.db.delete(entitlement)
            self.db.flush()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ==========================================
    # P2 TASK 10: SAAS SUBSCRIPTION & BILLING OVERSIGHT
    # ==========================================

    def list_subscriptions(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        plan_id: int | None = None,
        tenant_id: int | None = None,
        has_pending_plan: bool | None = None,
        has_scheduled_plan: bool | None = None,
    ) -> dict:
        valid_statuses = {"trialing", "active", "past_due", "cancelled", "expired"}
        if status:
            norm_status = status.strip().lower()
            if norm_status not in valid_statuses:
                raise AppException(
                    detail=f"Invalid subscription status: '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}",
                    status_code=400,
                )

        query = (
            self.db.query(SaaSSubscription)
            .options(
                joinedload(SaaSSubscription.tenant),
                joinedload(SaaSSubscription.plan),
                joinedload(SaaSSubscription.pending_plan),
                joinedload(SaaSSubscription.scheduled_plan),
            )
        )

        if status:
            query = query.filter(SaaSSubscription.status == status.strip().lower())
        if plan_id is not None:
            query = query.filter(SaaSSubscription.plan_id == plan_id)
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)
        if has_pending_plan is True:
            query = query.filter(SaaSSubscription.pending_plan_id.isnot(None))
        elif has_pending_plan is False:
            query = query.filter(SaaSSubscription.pending_plan_id.is_(None))
        if has_scheduled_plan is True:
            query = query.filter(SaaSSubscription.scheduled_plan_id.isnot(None))
        elif has_scheduled_plan is False:
            query = query.filter(SaaSSubscription.scheduled_plan_id.is_(None))

        total = query.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        subscriptions = (
            query.order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for sub in subscriptions:
            tenant_name = sub.tenant.name if sub.tenant else ""
            tenant_domain = sub.tenant.domain if sub.tenant else None

            current_plan = (
                SuperAdminPlanSummary(
                    id=sub.plan.id,
                    code=sub.plan.code,
                    name=sub.plan.name,
                    price=sub.plan.price,
                    currency=sub.plan.currency,
                    billing_interval=sub.plan.billing_interval,
                )
                if sub.plan
                else None
            )

            pending_plan = (
                SuperAdminPlanSummary(
                    id=sub.pending_plan.id,
                    code=sub.pending_plan.code,
                    name=sub.pending_plan.name,
                    price=sub.pending_plan.price,
                    currency=sub.pending_plan.currency,
                    billing_interval=sub.pending_plan.billing_interval,
                )
                if sub.pending_plan
                else None
            )

            scheduled_plan = (
                SuperAdminPlanSummary(
                    id=sub.scheduled_plan.id,
                    code=sub.scheduled_plan.code,
                    name=sub.scheduled_plan.name,
                    price=sub.scheduled_plan.price,
                    currency=sub.scheduled_plan.currency,
                    billing_interval=sub.scheduled_plan.billing_interval,
                )
                if sub.scheduled_plan
                else None
            )

            items.append(
                SuperAdminSubscriptionListItem(
                    subscription_id=sub.id,
                    tenant_id=sub.tenant_id,
                    tenant_name=tenant_name,
                    tenant_domain=tenant_domain,
                    status=sub.status,
                    current_plan=current_plan,
                    pending_plan=pending_plan,
                    scheduled_plan=scheduled_plan,
                    unit_price=sub.unit_price,
                    currency=sub.currency,
                    billing_interval=sub.billing_interval,
                    start_date=sub.start_date,
                    current_period_start=sub.current_period_start,
                    current_period_end=sub.current_period_end,
                    trial_end_date=sub.trial_end_date,
                    cancel_at_period_end=sub.cancel_at_period_end,
                    cancelled_at=sub.cancelled_at,
                )
            )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_tenant_subscription(self, tenant_id: int) -> dict:
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")

        if not tenant.current_subscription_id:
            return {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tenant_domain": tenant.domain,
                "has_subscription": False,
                "subscription": None,
                "current_plan": None,
                "pending_plan": None,
                "scheduled_plan": None,
                "usage_summary": [],
                "recent_invoices": [],
                "latest_unpaid_invoice": None,
            }

        sub = (
            self.db.query(SaaSSubscription)
            .options(
                joinedload(SaaSSubscription.plan),
                joinedload(SaaSSubscription.pending_plan),
                joinedload(SaaSSubscription.scheduled_plan),
            )
            .filter(SaaSSubscription.id == tenant.current_subscription_id)
            .first()
        )

        if not sub:
            return {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tenant_domain": tenant.domain,
                "has_subscription": False,
                "subscription": None,
                "current_plan": None,
                "pending_plan": None,
                "scheduled_plan": None,
                "usage_summary": [],
                "recent_invoices": [],
                "latest_unpaid_invoice": None,
            }

        if sub.tenant_id != tenant.id:
            raise ConflictException(
                detail=f"Subscription {sub.id} does not belong to tenant {tenant.id}"
            )

        entitlement_svc = SaaSEntitlementService(self.db)
        usage_summary = []
        for dim in ["stores", "users", "products"]:
            usage = entitlement_svc.get_usage(tenant.id, dim)
            try:
                limit, is_unlimited = entitlement_svc.get_limit(tenant.id, dim)
            except Exception:
                limit, is_unlimited = None, False
            usage_summary.append(
                SuperAdminEntitlementUsage(
                    dimension=dim,
                    current_usage=usage,
                    limit=limit,
                    is_unlimited=is_unlimited,
                )
            )

        recent_invoices_models = (
            self.db.query(SaaSInvoice)
            .filter(SaaSInvoice.tenant_id == tenant.id)
            .order_by(SaaSInvoice.created_at.desc(), SaaSInvoice.id.desc())
            .limit(5)
            .all()
        )
        recent_invoices = [
            SaaSInvoiceResponse.model_validate(inv) for inv in recent_invoices_models
        ]

        latest_unpaid_model = (
            self.db.query(SaaSInvoice)
            .filter(
                SaaSInvoice.tenant_id == tenant.id,
                SaaSInvoice.status == "unpaid",
            )
            .order_by(SaaSInvoice.created_at.desc(), SaaSInvoice.id.desc())
            .first()
        )
        latest_unpaid_invoice = (
            SaaSInvoiceResponse.model_validate(latest_unpaid_model)
            if latest_unpaid_model
            else None
        )

        current_plan = (
            SuperAdminPlanSummary(
                id=sub.plan.id,
                code=sub.plan.code,
                name=sub.plan.name,
                price=sub.plan.price,
                currency=sub.plan.currency,
                billing_interval=sub.plan.billing_interval,
            )
            if sub.plan
            else None
        )

        pending_plan = (
            SuperAdminPlanSummary(
                id=sub.pending_plan.id,
                code=sub.pending_plan.code,
                name=sub.pending_plan.name,
                price=sub.pending_plan.price,
                currency=sub.pending_plan.currency,
                billing_interval=sub.pending_plan.billing_interval,
            )
            if sub.pending_plan
            else None
        )

        scheduled_plan = (
            SuperAdminPlanSummary(
                id=sub.scheduled_plan.id,
                code=sub.scheduled_plan.code,
                name=sub.scheduled_plan.name,
                price=sub.scheduled_plan.price,
                currency=sub.scheduled_plan.currency,
                billing_interval=sub.scheduled_plan.billing_interval,
            )
            if sub.scheduled_plan
            else None
        )

        sub_info = SuperAdminSubscriptionDetailInfo(
            id=sub.id,
            status=sub.status,
            billing_interval=sub.billing_interval,
            unit_price=sub.unit_price,
            currency=sub.currency,
            start_date=sub.start_date,
            current_period_start=sub.current_period_start,
            current_period_end=sub.current_period_end,
            trial_end_date=sub.trial_end_date,
            cancel_at_period_end=sub.cancel_at_period_end,
            cancelled_at=sub.cancelled_at,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tenant_domain": tenant.domain,
            "has_subscription": True,
            "subscription": sub_info,
            "current_plan": current_plan,
            "pending_plan": pending_plan,
            "scheduled_plan": scheduled_plan,
            "usage_summary": usage_summary,
            "recent_invoices": recent_invoices,
            "latest_unpaid_invoice": latest_unpaid_invoice,
        }

    def list_invoices(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        billing_reason: str | None = None,
        tenant_id: int | None = None,
        search: str | None = None,
    ) -> dict:
        valid_statuses = {"unpaid", "paid", "cancelled"}
        if status:
            norm_status = status.strip().lower()
            if norm_status not in valid_statuses:
                raise AppException(
                    detail=f"Invalid invoice status: '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}",
                    status_code=400,
                )

        valid_reasons = {
            "trial_conversion",
            "subscription_cycle",
            "plan_upgrade",
            "manual_renewal",
        }
        if billing_reason:
            norm_reason = billing_reason.strip().lower()
            if norm_reason not in valid_reasons:
                raise AppException(
                    detail=f"Invalid billing reason: '{billing_reason}'. Must be one of: {', '.join(sorted(valid_reasons))}",
                    status_code=400,
                )

        query = self.db.query(SaaSInvoice).options(joinedload(SaaSInvoice.tenant))

        if status:
            query = query.filter(SaaSInvoice.status == status.strip().lower())
        if billing_reason:
            query = query.filter(SaaSInvoice.billing_reason == billing_reason.strip().lower())
        if tenant_id is not None:
            query = query.filter(SaaSInvoice.tenant_id == tenant_id)
        if search:
            query = query.filter(
                func.lower(SaaSInvoice.invoice_number).like(f"%{search.strip().lower()}%")
            )

        total = query.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        invoices = (
            query.order_by(
                SaaSInvoice.created_at.desc(),
                SaaSInvoice.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for inv in invoices:
            tenant_name = inv.tenant.name if inv.tenant else ""
            items.append(
                SuperAdminInvoiceListItem(
                    invoice_id=inv.id,
                    invoice_number=inv.invoice_number,
                    tenant_id=inv.tenant_id,
                    tenant_name=tenant_name,
                    subscription_id=inv.subscription_id,
                    billing_reason=inv.billing_reason,
                    subtotal=inv.subtotal,
                    tax_amount=inv.tax_amount,
                    total_amount=inv.total_amount,
                    currency=inv.currency,
                    status=inv.status,
                    due_date=inv.due_date,
                    paid_at=inv.paid_at,
                    created_at=inv.created_at,
                )
            )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_invoice(self, invoice_id: int) -> dict:
        invoice = (
            self.db.query(SaaSInvoice)
            .options(
                joinedload(SaaSInvoice.tenant),
                joinedload(SaaSInvoice.subscription).joinedload(SaaSSubscription.plan),
            )
            .filter(SaaSInvoice.id == invoice_id)
            .first()
        )
        if not invoice:
            raise NotFoundException(f"Invoice {invoice_id} not found")

        tenant_resp = (
            SuperAdminTenantSummary(
                id=invoice.tenant.id,
                name=invoice.tenant.name,
                domain=invoice.tenant.domain,
                is_active=invoice.tenant.is_active,
            )
            if invoice.tenant
            else None
        )

        sub = invoice.subscription
        sub_resp = None
        current_plan_resp = None
        if sub:
            sub_resp = SuperAdminSubscriptionDetailInfo(
                id=sub.id,
                status=sub.status,
                billing_interval=sub.billing_interval,
                unit_price=sub.unit_price,
                currency=sub.currency,
                start_date=sub.start_date,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                trial_end_date=sub.trial_end_date,
                cancel_at_period_end=sub.cancel_at_period_end,
                cancelled_at=sub.cancelled_at,
                created_at=sub.created_at,
                updated_at=sub.updated_at,
            )
            if sub.plan:
                current_plan_resp = SuperAdminPlanSummary(
                    id=sub.plan.id,
                    code=sub.plan.code,
                    name=sub.plan.name,
                    price=sub.plan.price,
                    currency=sub.plan.currency,
                    billing_interval=sub.plan.billing_interval,
                )

        upi_transactions_models = (
            self.db.query(SaaSUPITransaction)
            .filter(SaaSUPITransaction.invoice_id == invoice.id)
            .order_by(
                SaaSUPITransaction.created_at.desc(),
                SaaSUPITransaction.id.desc(),
            )
            .all()
        )
        upi_transactions = [
            UPITransactionResponse.model_validate(tx) for tx in upi_transactions_models
        ]
        latest_upi_transaction = upi_transactions[0] if upi_transactions else None

        return {
            "invoice": SaaSInvoiceResponse.model_validate(invoice),
            "tenant": tenant_resp,
            "subscription": sub_resp,
            "current_plan": current_plan_resp,
            "upi_transactions": upi_transactions,
            "latest_upi_transaction": latest_upi_transaction,
        }
