from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SignalEvent(Base):
    __tablename__ = "signal_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    company_domain: Mapped[str | None] = mapped_column(Text)
    signal_type: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_signal_events_source_observed", "source", "observed_at"),
        Index("ix_signal_events_company_domain", "company_domain"),
        Index("ix_signal_events_normalized_gin", "normalized", postgresql_using="gin"),
    )


class IcpCompany(Base):
    __tablename__ = "icp_companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    alt_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    hubspot_company_id: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_icp_companies_domain",
            "domain",
            unique=True,
            postgresql_where=text("domain IS NOT NULL"),
        ),
        Index("ix_icp_companies_aliases_gin", "aliases", postgresql_using="gin"),
        Index("ix_icp_companies_alt_domains_gin", "alt_domains", postgresql_using="gin"),
    )


class ScoredSignal(Base):
    __tablename__ = "scored_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    signal_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("signal_events.id"), nullable=False
    )
    icp_company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("icp_companies.id")
    )
    match_method: Mapped[str] = mapped_column(Text, nullable=False)
    match_confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    signal_strength: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    recency_decay: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    icp_fit: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    signal_category: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    slack_ts: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_scored_signals_unpublished",
            "published_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_scored_signals_score", "score", "created_at"),
        Index("ix_scored_signals_event", "signal_event_id"),
    )


class ManualOverride(Base):
    __tablename__ = "manual_overrides"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scored_signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scored_signals.id")
    )
    slack_user_id: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    rule_type: Mapped[str | None] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(Text)
    rule_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    signals_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    signals_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    __table_args__ = (Index("ix_source_runs_source_started", "source", "started_at"),)
