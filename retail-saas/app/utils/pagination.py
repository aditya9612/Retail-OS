from typing import Any, Optional, Sequence, Tuple
from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session


def compute_total_pages(total: int, page_size: Optional[int]) -> int:
    """Compute 1-based total pages from total record count and page size."""
    if total <= 0:
        return 0
    if not page_size or page_size <= 0:
        return 1
    return (total + page_size - 1) // page_size


def paginate_query(
    query: Query,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    default_page_size: int = 20,
) -> Tuple[list[Any], int, int, int, int]:
    """
    Execute count and paginated fetch on a SQLAlchemy query.
    Returns (items, total, effective_page, effective_page_size, total_pages).
    """
    total = query.count()
    if page is None and page_size is None:
        items = query.all()
        eff_page = 1
        eff_size = len(items) if items else 0
        total_pages = 1 if total > 0 else 0
        return items, total, eff_page, eff_size, total_pages

    eff_page = page if (page is not None and page >= 1) else 1
    eff_size = page_size if (page_size is not None and page_size >= 1) else default_page_size
    offset = (eff_page - 1) * eff_size
    items = query.offset(offset).limit(eff_size).all()
    total_pages = compute_total_pages(total, eff_size)
    return items, total, eff_page, eff_size, total_pages


def count_boolean_flag(
    db: Session,
    model: Any,
    tenant_id: int,
    flag_col: Any,
    extra_filters: Optional[Sequence[Any]] = None,
) -> dict[str, int]:
    """Single SQL query returning total, active (True), and inactive (False) counts."""
    query = db.query(
        func.count(model.id).label("total"),
        func.count(case((flag_col.is_(True), 1))).label("active"),
        func.count(case((flag_col.is_(False), 1))).label("inactive"),
    ).filter(model.tenant_id == tenant_id)
    if extra_filters:
        for f in extra_filters:
            query = query.filter(f)
    row = query.one()
    return {
        "total": int(row.total or 0),
        "active": int(row.active or 0),
        "inactive": int(row.inactive or 0),
    }


def count_by_status(
    db: Session,
    model: Any,
    tenant_id: int,
    status_col: Any,
    statuses: Sequence[str],
    extra_filters: Optional[Sequence[Any]] = None,
    joins: Optional[Sequence[Tuple[Any, Any]]] = None,
) -> dict[str, int]:
    """Single GROUP BY query returning total and per-status counts."""
    query = db.query(status_col, func.count(model.id))
    if joins:
        for target, onclause in joins:
            query = query.join(target, onclause)
    query = query.filter(model.tenant_id == tenant_id)
    if extra_filters:
        for f in extra_filters:
            query = query.filter(f)
    rows = query.group_by(status_col).all()
    by_status = {str(s).lower(): int(c) for s, c in rows if s is not None}
    result = {"total": sum(by_status.values())}
    for s in statuses:
        result[s] = by_status.get(s, 0)
    return result
