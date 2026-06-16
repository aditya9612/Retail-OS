from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return AuthService(db).login(data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return AuthService(db).refresh(data.refresh_token)


@router.post("/register")
def register(
    tenant_name: str,
    slug: str,
    email: str,
    admin_name: str,
    password: str,
    phone: str | None = None,
    db: Session = Depends(get_db),
):
    user = AuthService(db).register_tenant(tenant_name, slug, email, admin_name, password, phone)
    return {"message": "Tenant registered", "user_id": user.id, "tenant_id": user.tenant_id}
