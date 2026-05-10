"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("company_domain", sa.Text()),
        sa.Column("signal_type", sa.Text()),
    )
    op.create_index(
        "ix_signal_events_source_observed", "signal_events", ["source", "observed_at"]
    )
    op.create_index("ix_signal_events_company_domain", "signal_events", ["company_domain"])
    op.create_index(
        "ix_signal_events_normalized_gin",
        "signal_events",
        ["normalized"],
        postgresql_using="gin",
    )

    op.create_table(
        "icp_companies",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text()),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "alt_domains",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("hubspot_company_id", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_icp_companies_domain",
        "icp_companies",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index(
        "ix_icp_companies_aliases_gin", "icp_companies", ["aliases"], postgresql_using="gin"
    )
    op.create_index(
        "ix_icp_companies_alt_domains_gin",
        "icp_companies",
        ["alt_domains"],
        postgresql_using="gin",
    )

    op.create_table(
        "scored_signals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "signal_event_id",
            sa.BigInteger(),
            sa.ForeignKey("signal_events.id"),
            nullable=False,
        ),
        sa.Column("icp_company_id", sa.BigInteger(), sa.ForeignKey("icp_companies.id")),
        sa.Column("match_method", sa.Text(), nullable=False),
        sa.Column("match_confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("signal_strength", sa.Numeric(3, 2), nullable=False),
        sa.Column("recency_decay", sa.Numeric(3, 2), nullable=False),
        sa.Column("icp_fit", sa.Numeric(3, 2), nullable=False),
        sa.Column("score", sa.Numeric(4, 2), nullable=False),
        sa.Column("signal_category", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("slack_ts", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_scored_signals_unpublished",
        "scored_signals",
        ["published_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_scored_signals_score", "scored_signals", ["score", "created_at"])
    op.create_index("ix_scored_signals_event", "scored_signals", ["signal_event_id"])

    op.create_table(
        "manual_overrides",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scored_signal_id", sa.BigInteger(), sa.ForeignKey("scored_signals.id")),
        sa.Column("slack_user_id", sa.Text()),
        sa.Column("feedback", sa.Text()),
        sa.Column("rule_type", sa.Text()),
        sa.Column("target", sa.Text()),
        sa.Column("rule_config", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "source_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("signals_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("signals_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.create_index("ix_source_runs_source_started", "source_runs", ["source", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_source_runs_source_started", table_name="source_runs")
    op.drop_table("source_runs")
    op.drop_table("manual_overrides")
    op.drop_index("ix_scored_signals_event", table_name="scored_signals")
    op.drop_index("ix_scored_signals_score", table_name="scored_signals")
    op.drop_index("ix_scored_signals_unpublished", table_name="scored_signals")
    op.drop_table("scored_signals")
    op.drop_index("ix_icp_companies_alt_domains_gin", table_name="icp_companies")
    op.drop_index("ix_icp_companies_aliases_gin", table_name="icp_companies")
    op.drop_index("ix_icp_companies_domain", table_name="icp_companies")
    op.drop_table("icp_companies")
    op.drop_index("ix_signal_events_normalized_gin", table_name="signal_events")
    op.drop_index("ix_signal_events_company_domain", table_name="signal_events")
    op.drop_index("ix_signal_events_source_observed", table_name="signal_events")
    op.drop_table("signal_events")
