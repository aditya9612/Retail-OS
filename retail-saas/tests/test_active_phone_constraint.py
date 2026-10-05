import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.core.database import SessionLocal


def test_active_phone_unique_constraint():
    db = SessionLocal()
    created_role = False
    role = None
    try:
        # Create test tenant 1 & 2
        t1 = Tenant(name="Tenant 1", domain="tenant-1-phone-test", is_active=True)
        t2 = Tenant(name="Tenant 2", domain="tenant-2-phone-test", is_active=True)
        db.add_all([t1, t2])
        db.commit()
        db.refresh(t1)
        db.refresh(t2)

        # Get or create role with admin permissions so no global state pollution occurs
        role = db.query(Role).first()
        if not role:
            role = Role(name="admin", tenant_id=None, is_system=True, permissions=["*"])
            db.add(role)
            db.commit()
            db.refresh(role)
            created_role = True

        phone_num = "9876543210"
        diff_phone_num = "8888888888"

        # 1. User A in Tenant 1 with phone_num -> Must SUCCEED
        user_a = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="usera@test1.com",
            password_hash="fakehash",
            full_name="User A",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_a)
        db.commit()
        db.refresh(user_a)
        assert user_a.active_phone == phone_num

        # 2. User B in Tenant 2 with SAME phone_num -> Must FAIL with IntegrityError (global uniqueness)
        user_b = User(
            tenant_id=t2.id,
            role_id=role.id,
            email="userb@test2.com",
            password_hash="fakehash",
            full_name="User B",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_b)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 3. User B2 in Tenant 2 with DIFFERENT phone_num -> Must SUCCEED
        user_b2 = User(
            tenant_id=t2.id,
            role_id=role.id,
            email="userb2@test2.com",
            password_hash="fakehash",
            full_name="User B2",
            phone=diff_phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_b2)
        db.commit()
        db.refresh(user_b2)
        assert user_b2.active_phone == diff_phone_num

        # 4. User C in Tenant 1 with SAME phone_num as User A -> Must FAIL with IntegrityError
        user_c = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="userc@test1.com",
            password_hash="fakehash",
            full_name="User C",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_c)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 5. Soft-delete User A (is_deleted = True) -> active_phone becomes NULL
        user_a = db.query(User).filter(User.id == user_a.id).first()
        user_a.is_deleted = True
        db.commit()
        db.refresh(user_a)
        assert user_a.active_phone is None

        # 6. Now create User D in Tenant 2 with SAME phone_num -> Must SUCCEED because User A is soft-deleted
        user_d = User(
            tenant_id=t2.id,
            role_id=role.id,
            email="userd@test2.com",
            password_hash="fakehash",
            full_name="User D",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_d)
        db.commit()
        db.refresh(user_d)
        assert user_d.active_phone == phone_num

        # 7. Attempt to restore User A (is_deleted = False) while User D is active with same phone -> Must FAIL
        user_a = db.query(User).filter(User.id == user_a.id).first()
        user_a.is_deleted = False
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 8. Multiple users with phone=None -> Must SUCCEED (NULLs do not collide in unique constraint)
        user_none1 = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="none1@test1.com",
            password_hash="fakehash",
            full_name="User None 1",
            phone=None,
            is_deleted=False,
            is_active=True,
        )
        user_none2 = User(
            tenant_id=t2.id,
            role_id=role.id,
            email="none2@test2.com",
            password_hash="fakehash",
            full_name="User None 2",
            phone=None,
            is_deleted=False,
            is_active=True,
        )
        db.add_all([user_none1, user_none2])
        db.commit()

    finally:
        db.rollback()
        # Clean up
        db.query(User).filter(User.email.in_([
            "usera@test1.com", "userb@test2.com", "userb2@test2.com", "userc@test1.com",
            "userd@test2.com", "none1@test1.com", "none2@test2.com"
        ])).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.domain.in_(["tenant-1-phone-test", "tenant-2-phone-test"])).delete(synchronize_session=False)
        if created_role and role:
            db.query(Role).filter(Role.id == role.id).delete(synchronize_session=False)
        db.commit()
        db.close()
