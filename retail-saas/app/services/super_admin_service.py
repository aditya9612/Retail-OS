import math
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
from app.models.role import Role
from app.models.saas_billing import SaaSPlan
from app.models.store import Store
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.schemas.saas_entitlement import (
    SaaSPlanEntitlementCreate,
    SaaSPlanEntitlementUpdate,
)
from app.schemas.saas_plan import (
    SaaSPlanCreate,
    SaaSPlanUpdate,
)
from app.schemas.super_admin import (
    SuperAdminChangePassword,
    SuperAdminCreate,
    SuperAdminLogin,
    SuperAdminUpdate,
)


class SuperAdminService:

    def __init__(self, db: Session):
        self.db = db

    def create_super_admin(
        self,
        data: SuperAdminCreate,
    ) -> SuperAdmin:
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

        return {
            "total_super_admins": total_super_admins,
            "active_super_admins": active_super_admins,
            "inactive_super_admins": inactive_super_admins,
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "inactive_tenants": inactive_tenants,
            "total_users": total_users,
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