from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import (
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
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
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

    def list_super_admins(self):
        return (
            self.db.query(SuperAdmin)
            .order_by(SuperAdmin.id.desc())
            .all()
        )

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

    def list_tenants(self):
        return (
            self.db.query(Tenant)
            .order_by(Tenant.id.desc())
            .all()
        )

    def get_tenant(
        self,
        tenant_id: int,
    ) -> Tenant:
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

        return tenant

    def update_tenant_status(
        self,
        tenant_id: int,
        is_active: bool,
    ):
        tenant = self.get_tenant(
            tenant_id
        )

        if not hasattr(tenant, "is_active"):
            raise ConflictException(
                "Tenant model does not support active status"
            )

        tenant.is_active = is_active

        self.db.commit()
        self.db.refresh(tenant)

        return tenant

    def list_tenant_users(
        self,
        tenant_id: int,
    ):
        self.get_tenant(tenant_id)

        return (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id
            )
            .order_by(User.id.desc())
            .all()
        )

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