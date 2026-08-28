"""SQLAlchemy models for the local portfolio ledger.

Mirror tables (holdings_current, transactions, …) are payload_json blobs that
shadow Sheet tabs. Evidence tables (signal_events, bars_daily,
fundamentals_snapshot) are typed, append-only, and SQLite-only.

No Alembic: Base.metadata.create_all creates *missing* tables only. A changed
column on an existing table will not migrate — get evidence schemas right now.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

import config

logger = logging.getLogger(__name__)

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


def _warn_if_drive_synced(db_path: Path) -> None:
    """Warn when the live ledger sits inside a Drive-synced tree (WAL corruption risk)."""
    markers = (".tmp.drivedownload", ".tmp.driveupload")
    try:
        resolved = db_path.resolve()
    except OSError:
        resolved = db_path
    for parent in [resolved.parent, *resolved.parents]:
        for marker in markers:
            if (parent / marker).exists():
                # stdout (not logger.warning→stderr): PowerShell wraps stderr as NativeCommandError
                print(
                    f"WARNING: SQLITE_DB_PATH {resolved} is under a Drive-synced tree "
                    f"({marker} present at {parent}). Relocate off Drive to avoid WAL corruption.",
                    flush=True,
                )
                return


class JudgmentCampaign(Base):
    """Latest lifecycle artifact per ticker — freshness for Position Story."""

    __tablename__ = "judgment_campaigns"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    json_path: Mapped[str] = mapped_column(String(512), nullable=False)
    legs: Mapped[int] = mapped_column(Integer, default=0)
    retrieval_hash: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UiRun(Base):
    """Desk launcher history — Tier 0 subprocess runs from POST /run/{routine_id}."""

    __tablename__ = "ui_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routine_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


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


class SignalEvent(Base):
    """Append-only Crosshairs / dislocation / level-coverage signal record."""

    __tablename__ = "signal_events"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_signal_events_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    distance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_bucket: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    doctrine_downgraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)


class BarDaily(Base):
    """Append-only daily OHLCV. Source is part of the unique key (not a tiebreak)."""

    __tablename__ = "bars_daily"
    __table_args__ = (
        UniqueConstraint("ticker", "bar_date", "source", name="uq_bars_daily_ticker_date_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    bar_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FundamentalsSnapshot(Base):
    """Append-only per-ticker fundamentals snapshot for one as-of date."""

    __tablename__ = "fundamentals_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "as_of_date", "source", name="uq_fundamentals_snapshot_ticker_date_source"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fwd_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_to_book: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    week52_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    week52_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class CorpusDoc(Base):
    """One row per corpus source file. sha256 drives incremental re-index."""

    __tablename__ = "corpus_docs"
    __table_args__ = (UniqueConstraint("path", name="uq_corpus_docs_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    date_is_inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tickers: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mtime: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_bills_writing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_model_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CorpusChunk(Base):
    """One chunk per corpus_docs row slice; line_start/line_end are citation coords."""

    __tablename__ = "corpus_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chunk_ix: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True)


class RetrievalLog(Base):
    """One row per retrieve() call — write path only (not via read-only URI)."""

    __tablename__ = "retrieval_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    caller: Mapped[str] = mapped_column(String(128), nullable=False, default="cli")
    template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    corpus_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RationaleProposal(Base):
    """
    Rationale-loop proposal. Append-only on create; resolution updates in place
    without overwriting proposal_text (resolved_text is a separate column).
    """

    __tablename__ = "rationale_proposals"
    __table_args__ = (
        UniqueConstraint(
            "cluster_fingerprint", "proposed_at", name="uq_rationale_proposals_fp_at"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    proposal_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_strength: Mapped[str] = mapped_column(String(16), nullable=False)  # strong|weak|none
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    retrieval_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open"
    )  # closed vocab: open|confirmed|edited|rejected|deferred|void_scope
    # void_scope = outside signed-off population / written in error — NOT dismissed
    # (prompt 10 must not treat as rejected). See prompts/rationale_loop_2026-08-27.md.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_provenance: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # declared_before|reconstructed_after
    batch_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sell_tickers: Mapped[str | None] = mapped_column(Text, nullable=True)
    buy_tickers: Mapped[str | None] = mapped_column(Text, nullable=True)


class Precommitment(Base):
    """
    Dated declaration that a thesis band will be acted on if crossed.
    Thesis frontmatter remains authoritative on the band; this row is the
    decision record. Band moves do not mutate existing rows.
    """

    __tablename__ = "precommitments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    band_side: Mapped[str] = mapped_column(String(8), nullable=False)  # trim|add
    band_level: Mapped[float] = mapped_column(Float, nullable=False)
    intended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="cli")  # cli|thesis_sync
    thesis_band_at_declaration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open"
    )  # open|fired|closed_band_moved|closed_position_exited|closed_manual
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrecommitmentFiring(Base):
    """
    One row per (precommitment, signal_event) crossing. response starts pending
    and is only ever set by an explicit operator action — never inferred.
    """

    __tablename__ = "precommitment_firings"
    __table_args__ = (
        UniqueConstraint(
            "precommitment_id",
            "signal_event_id",
            name="uq_precommitment_firings_pc_sig",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    precommitment_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    signal_event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    response: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending|acted|passed
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_trade_log_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doctrine_downgraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


_engine = None
_SessionLocal = None


def ensure_corpus_fts(conn=None) -> None:
    """FTS5 virtual table — SQLAlchemy does not model these; raw DDL only."""
    ddl = """
    CREATE VIRTUAL TABLE IF NOT EXISTS corpus_fts USING fts5(
      body,
      chunk_id UNINDEXED,
      doc_id UNINDEXED,
      source_type UNINDEXED,
      path UNINDEXED,
      doc_date UNINDEXED,
      tickers UNINDEXED,
      tokenize = "unicode61 remove_diacritics 2"
    )
    """
    if conn is not None:
        conn.execute(ddl)
        return
    eng = get_engine()
    with eng.begin() as c:
        c.exec_driver_sql(ddl)


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        path = Path(config.SQLITE_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _warn_if_drive_synced(path)
        url = f"sqlite:///{path.as_posix()}"
        _engine = create_engine(url, future=True)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        with _engine.begin() as c:
            c.exec_driver_sql(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS corpus_fts USING fts5(
                  body,
                  chunk_id UNINDEXED,
                  doc_id UNINDEXED,
                  source_type UNINDEXED,
                  path UNINDEXED,
                  doc_date UNINDEXED,
                  tickers UNINDEXED,
                  tokenize = "unicode61 remove_diacritics 2"
                )
                """
            )
    return _engine


def get_session():
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()
