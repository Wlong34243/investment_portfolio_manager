"""SQLAlchemy models for the local portfolio ledger."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

import config

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(128), nullable=False)
    live: Mapped[bool] = mapped_column(Boolean, default=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MetaKV(Base):
    """Key/value bag for tax metrics, decision header, etc."""

    __tablename__ = "meta_kv"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class HoldingsCurrentRow(Base):
    __tablename__ = "holdings_current"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class TransactionRow(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class TradeLogRow(Base):
    __tablename__ = "trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class TradeLogStagingRow(Base):
    __tablename__ = "trade_log_staging"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class RealizedGLRow(Base):
    __tablename__ = "realized_gl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class RotationReviewRow(Base):
    __tablename__ = "rotation_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class TaxControlLotRow(Base):
    __tablename__ = "tax_control_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class DecisionViewRow(Base):
    __tablename__ = "decision_view"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        path = config.SQLITE_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path.as_posix()}"
        _engine = create_engine(url, future=True)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session():
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()
