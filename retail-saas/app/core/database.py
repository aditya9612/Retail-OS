from datetime import datetime
from typing import Generator
from urllib.parse import unquote, urlparse

from sqlalchemy import DateTime, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import get_settings


settings = get_settings()


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {}

    return {"charset": "utf8mb4"}


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
    connect_args=_connect_args(settings.DATABASE_URL),
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


def get_db() -> Generator:
    db = SessionLocal()

    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    return unquote(parsed.path.lstrip("/"))


def ensure_database_exists(database_url: str | None = None) -> None:


    url = database_url or settings.DATABASE_URL

    db_name = get_database_name(url)

    if not db_name:
        raise ValueError("DATABASE_URL must include a database name")

    parsed = urlparse(url)

    server_url = (
        f"{parsed.scheme}://{parsed.netloc}/"
        if parsed.scheme
        else url.rsplit("/", 1)[0] + "/"
    )

    bootstrap_engine = create_engine(
        server_url,
        pool_pre_ping=True,
        connect_args={"charset": "utf8mb4"},
    )

    with bootstrap_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 "
                "COLLATE utf8mb4_unicode_ci"
            )
        )

        connection.commit()

    bootstrap_engine.dispose()


def ensure_schema_compatibility() -> None:
    if settings.DATABASE_URL.startswith("sqlite"):
        return
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "roles" in tables:
            columns = {c["name"] for c in inspector.get_columns("roles")}
            if "is_system" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE roles ADD COLUMN is_system TINYINT(1) NOT NULL DEFAULT 0")
                    )
        if "users" in tables:
            columns = {c["name"] for c in inspector.get_columns("users")}
            if "hashed_password" in columns and "password_hash" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE users CHANGE COLUMN hashed_password password_hash VARCHAR(255) NOT NULL")
                    )
        if "tenants" in tables:
            columns = {c["name"] for c in inspector.get_columns("tenants")}
            if "slug" in columns and "domain" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE tenants CHANGE COLUMN slug domain VARCHAR(255) NOT NULL")
                    )
            elif "domain" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE tenants ADD COLUMN domain VARCHAR(255) NOT NULL DEFAULT ''")
                    )
            if "settings" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE tenants ADD COLUMN settings JSON NULL")
                    )
            if "current_subscription_id" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE tenants ADD COLUMN current_subscription_id INT NULL")
                    )
        if "stores" in tables:
            columns = {c["name"] for c in inspector.get_columns("stores")}
            if "email" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN email VARCHAR(255) NULL")
                    )
            if "is_main" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN is_main TINYINT(1) NOT NULL DEFAULT 0")
                    )
            if "code" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN code VARCHAR(50) NULL")
                    )
            if "city" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN city VARCHAR(100) NULL")
                    )
            if "state" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN state VARCHAR(100) NULL")
                    )
            if "pincode" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN pincode VARCHAR(20) NULL")
                    )
        if "customers" in tables:
            columns = {c["name"] for c in inspector.get_columns("customers")}
            if "status" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'")
                    )
            if "segment" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN segment VARCHAR(20) NOT NULL DEFAULT 'new'")
                    )
            if "total_spend" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN total_spend INT NOT NULL DEFAULT 0")
                    )
            if "loyalty_points" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN loyalty_points INT NOT NULL DEFAULT 0")
                    )
            if "whatsapp_opt_in" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN whatsapp_opt_in TINYINT(1) NOT NULL DEFAULT 1")
                    )
            if "sms_opt_in" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN sms_opt_in TINYINT(1) NOT NULL DEFAULT 1")
                    )
            if "gstin" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE customers ADD COLUMN gstin VARCHAR(20) NULL")
                    )
        if "products" in tables:
            columns = {c["name"] for c in inspector.get_columns("products")}
            if "selling_price" not in columns and "price" in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products CHANGE COLUMN price selling_price NUMERIC(12,2) NOT NULL")
                    )
            if "tax_rate" not in columns and "gst_rate" in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products CHANGE COLUMN gst_rate tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0.00")
                    )
            if "cost_price" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products ADD COLUMN cost_price NUMERIC(10,2) NOT NULL DEFAULT 0.00")
                    )
            if "min_stock_alert" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products ADD COLUMN min_stock_alert INT NOT NULL DEFAULT 5")
                    )
            if "stock_status" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products ADD COLUMN stock_status VARCHAR(20) NOT NULL DEFAULT 'in_stock'")
                    )
            if "unit" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE products ADD COLUMN unit VARCHAR(20) NOT NULL DEFAULT 'pcs'")
                    )
        if "orders" in tables:
            columns = {c["name"] for c in inspector.get_columns("orders")}
            if "order_type" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders ADD COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'pos'")
                    )
            if "discount_amount" not in columns and "discount" in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders CHANGE COLUMN discount discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00")
                    )
            elif "discount_amount" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders ADD COLUMN discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00")
                    )
            if "tax_amount" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders ADD COLUMN tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0.00")
                    )
            if "delivery_address" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders ADD COLUMN delivery_address VARCHAR(500) NULL")
                    )
            if "delivery_pincode" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE orders ADD COLUMN delivery_pincode VARCHAR(20) NULL")
                    )
        if "order_items" in tables:
            columns = {c["name"] for c in inspector.get_columns("order_items")}
            if "variant_id" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE order_items ADD COLUMN variant_id INT NULL")
                    )
    except Exception:
        pass


def init_db() -> None:

    import app.models  # noqa: F401

    if not settings.DATABASE_URL.startswith("sqlite"):
        ensure_database_exists()
        ensure_schema_compatibility()

