from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        tenant_id: int,
        user_id: int | None,
        action: str,
        resource: str,
        resource_id: int | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry
