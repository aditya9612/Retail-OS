from datetime import datetime
from typing import Generator
from urllib.parse import unquote, urlparse

from sqlalchemy import DateTime, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import get_settings
from app.core.logger import logger


settings = get_settings()


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {}

    return {"charset": "utf8mb4"}


def _engine_kwargs(database_url: str) -> dict:
    kwargs = {
        "echo": False,
        "connect_args": _connect_args(database_url),
    }
    if not database_url.startswith("sqlite"):
        kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                "pool_size": 20,
                "max_overflow": 40,
                "pool_timeout": 30,
            }
        )
    return kwargs


engine = create_engine(
    settings.DATABASE_URL,
    **_engine_kwargs(settings.DATABASE_URL),
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
        try:
            Base.metadata.create_all(bind=engine)
        except Exception:
            pass
        return

    try:
        from sqlalchemy import text

        # 1. Fetch all existing tables and columns in a single fast query (~0.03s)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT TABLE_NAME, COLUMN_NAME "
                    "FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                )
            ).fetchall()

        existing_cols: dict[str, set[str]] = {}
        for tname, cname in rows:
            existing_cols.setdefault(tname.lower(), set()).add(cname.lower())

        # 2. Handle known legacy column renames and specific backwards-compatibility requirements
        if "roles" in existing_cols:
            if "is_system" not in existing_cols["roles"]:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `roles` ADD COLUMN `is_system` TINYINT(1) NOT NULL DEFAULT 0")
                        )
                    existing_cols["roles"].add("is_system")
                except Exception as exc:
                    logger.warning("Could not add roles.is_system: %s", exc)

        if "users" in existing_cols:
            user_cols = existing_cols["users"]
            if "hashed_password" in user_cols and "password_hash" not in user_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `users` CHANGE COLUMN `hashed_password` `password_hash` VARCHAR(255) NOT NULL")
                        )
                    user_cols.discard("hashed_password")
                    user_cols.add("password_hash")
                except Exception as exc:
                    logger.warning("Could not rename hashed_password: %s", exc)

        if "tenants" in existing_cols:
            tenant_cols = existing_cols["tenants"]
            if "slug" in tenant_cols and "domain" not in tenant_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `tenants` CHANGE COLUMN `slug` `domain` VARCHAR(255) NOT NULL")
                        )
                    tenant_cols.discard("slug")
                    tenant_cols.add("domain")
                except Exception as exc:
                    logger.warning("Could not rename tenants.slug: %s", exc)
            elif "domain" not in tenant_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `tenants` ADD COLUMN `domain` VARCHAR(255) NOT NULL DEFAULT ''")
                        )
                    tenant_cols.add("domain")
                except Exception as exc:
                    logger.warning("Could not add tenants.domain: %s", exc)

            if "settings" not in tenant_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `tenants` ADD COLUMN `settings` JSON NULL")
                        )
                    tenant_cols.add("settings")
                except Exception as exc:
                    logger.warning("Could not add tenants.settings: %s", exc)

            if "current_subscription_id" not in tenant_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `tenants` ADD COLUMN `current_subscription_id` INT NULL")
                        )
                    tenant_cols.add("current_subscription_id")
                except Exception as exc:
                    logger.warning("Could not add tenants.current_subscription_id: %s", exc)

        if "stores" in existing_cols:
            store_cols = existing_cols["stores"]
            store_additions = [
                ("email", "VARCHAR(255) NULL"),
                ("is_main", "TINYINT(1) NOT NULL DEFAULT 0"),
                ("code", "VARCHAR(50) NULL"),
                ("city", "VARCHAR(100) NULL"),
                ("state", "VARCHAR(100) NULL"),
                ("pincode", "VARCHAR(20) NULL"),
            ]
            for col_name, col_def in store_additions:
                if col_name not in store_cols:
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE `stores` ADD COLUMN `{col_name}` {col_def}")
                            )
                        store_cols.add(col_name)
                    except Exception as exc:
                        logger.warning("Could not add stores.%s: %s", col_name, exc)

        if "customers" in existing_cols:
            cust_cols = existing_cols["customers"]
            cust_additions = [
                ("status", "VARCHAR(20) NOT NULL DEFAULT 'active'"),
                ("segment", "VARCHAR(20) NOT NULL DEFAULT 'new'"),
                ("total_spend", "INT NOT NULL DEFAULT 0"),
                ("loyalty_points", "INT NOT NULL DEFAULT 0"),
                ("whatsapp_opt_in", "TINYINT(1) NOT NULL DEFAULT 1"),
                ("sms_opt_in", "TINYINT(1) NOT NULL DEFAULT 1"),
                ("gstin", "VARCHAR(20) NULL"),
            ]
            for col_name, col_def in cust_additions:
                if col_name not in cust_cols:
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE `customers` ADD COLUMN `{col_name}` {col_def}")
                            )
                        cust_cols.add(col_name)
                    except Exception as exc:
                        logger.warning("Could not add customers.%s: %s", col_name, exc)

        if "products" in existing_cols:
            prod_cols = existing_cols["products"]
            if "selling_price" not in prod_cols and "price" in prod_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `products` CHANGE COLUMN `price` `selling_price` NUMERIC(12,2) NOT NULL")
                        )
                    prod_cols.discard("price")
                    prod_cols.add("selling_price")
                except Exception as exc:
                    logger.warning("Could not rename products.price: %s", exc)

            if "tax_rate" not in prod_cols and "gst_rate" in prod_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `products` CHANGE COLUMN `gst_rate` `tax_rate` NUMERIC(5,2) NOT NULL DEFAULT 0.00")
                        )
                    prod_cols.discard("gst_rate")
                    prod_cols.add("tax_rate")
                except Exception as exc:
                    logger.warning("Could not rename products.gst_rate: %s", exc)

            prod_additions = [
                ("cost_price", "NUMERIC(10,2) NOT NULL DEFAULT 0.00"),
                ("min_stock_alert", "INT NOT NULL DEFAULT 5"),
                ("stock_status", "VARCHAR(20) NOT NULL DEFAULT 'in_stock'"),
                ("unit", "VARCHAR(20) NOT NULL DEFAULT 'pcs'"),
            ]
            for col_name, col_def in prod_additions:
                if col_name not in prod_cols:
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE `products` ADD COLUMN `{col_name}` {col_def}")
                            )
                        prod_cols.add(col_name)
                    except Exception as exc:
                        logger.warning("Could not add products.%s: %s", col_name, exc)

        if "orders" in existing_cols:
            order_cols = existing_cols["orders"]
            if "discount_amount" not in order_cols and "discount" in order_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `orders` CHANGE COLUMN `discount` `discount_amount` NUMERIC(12,2) NOT NULL DEFAULT 0.00")
                        )
                    order_cols.discard("discount")
                    order_cols.add("discount_amount")
                except Exception as exc:
                    logger.warning("Could not rename orders.discount: %s", exc)

            order_additions = [
                ("order_type", "VARCHAR(20) NOT NULL DEFAULT 'pos'"),
                ("discount_amount", "NUMERIC(12,2) NOT NULL DEFAULT 0.00"),
                ("tax_amount", "NUMERIC(12,2) NOT NULL DEFAULT 0.00"),
                ("delivery_address", "VARCHAR(500) NULL"),
                ("delivery_pincode", "VARCHAR(20) NULL"),
            ]
            for col_name, col_def in order_additions:
                if col_name not in order_cols:
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE `orders` ADD COLUMN `{col_name}` {col_def}")
                            )
                        order_cols.add(col_name)
                    except Exception as exc:
                        logger.warning("Could not add orders.%s: %s", col_name, exc)

        if "order_items" in existing_cols:
            if "variant_id" not in existing_cols["order_items"]:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE `order_items` ADD COLUMN `variant_id` INT NULL")
                        )
                    existing_cols["order_items"].add("variant_id")
                except Exception as exc:
                    logger.warning("Could not add order_items.variant_id: %s", exc)

        # 3. UNIVERSAL AUTO-SYNC: Automatically detect and add ANY missing column across ALL models
        for table_name, table in Base.metadata.tables.items():
            t_lower = table_name.lower()
            if t_lower not in existing_cols:
                continue
            table_cols = existing_cols[t_lower]
            for col in table.columns:
                c_lower = col.name.lower()
                if c_lower not in table_cols:
                    try:
                        col_type = col.type.compile(engine.dialect)
                        sql = f"ALTER TABLE `{table_name}` ADD COLUMN `{col.name}` {col_type} NULL"
                        with engine.begin() as conn:
                            conn.execute(text(sql))
                        table_cols.add(c_lower)
                        logger.info(
                            "Auto-synced missing column: %s.%s (%s)",
                            table_name,
                            col.name,
                            col_type,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Could not auto-sync column %s.%s: %s",
                            table_name,
                            col.name,
                            exc,
                        )

        # 4. Safely create any newly defined tables that don't exist yet
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as exc:
            logger.warning("Base.metadata.create_all encountered an exception: %s", exc)

    except Exception as exc:
        logger.error("ensure_schema_compatibility encountered an error: %s", exc)



def init_db() -> None:

    import app.models  # noqa: F401

    if not settings.DATABASE_URL.startswith("sqlite"):
        ensure_database_exists()
        ensure_schema_compatibility()

