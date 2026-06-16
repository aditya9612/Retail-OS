from datetime import datetime
from typing import Generator
from urllib.parse import unquote, urlparse

from sqlalchemy import DateTime, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
    connect_args={"charset": "utf8mb4"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    return unquote(parsed.path.lstrip("/"))


def ensure_database_exists(database_url: str | None = None) -> None:
    """Create the MySQL database if it does not exist."""
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
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        connection.commit()
    bootstrap_engine.dispose()


def init_db() -> None:
    """Ensure database exists and all tables are created."""
    import app.models  # noqa: F401 — register all models with Base.metadata

    ensure_database_exists()
    Base.metadata.create_all(bind=engine)
