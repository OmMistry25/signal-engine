from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signal_engine.db.models import ScoredSignal, SignalEvent
from signal_engine.matcher.account_matcher import AccountMatcher
from signal_engine.publishers.slack import SlackPublisher
from signal_engine.scoring.scorer import Scorer

log = structlog.get_logger(__name__)


async def process_new_events(
    session: AsyncSession,
    *,
    matcher: AccountMatcher | None = None,
    scorer: Scorer | None = None,
    publisher: SlackPublisher | None = None,
) -> dict[str, Any]:
    """Match → score → (optionally) publish events without a scored_signals row.

    Idempotent — events that already have a scored row are skipped. Re-scoring
    after a taxonomy change is a separate, explicit operation (not in v1).
    """
    matcher = matcher or await AccountMatcher.from_session(session)
    scorer = scorer or Scorer()
    if publisher is None:
        publisher = SlackPublisher.from_settings()

    stmt = (
        select(SignalEvent)
        .outerjoin(ScoredSignal, ScoredSignal.signal_event_id == SignalEvent.id)
        .where(ScoredSignal.id.is_(None))
        .order_by(SignalEvent.id)
    )
    result = await session.execute(stmt)
    events = list(result.scalars())

    processed = 0
    published = 0
    for event in events:
        match = matcher.match(event)
        icp = matcher.get_icp(match.icp_company_id)
        score_result = scorer.score(event, match, icp)

        scored = ScoredSignal(
            signal_event_id=event.id,
            icp_company_id=match.icp_company_id,
            match_method=match.match_method,
            match_confidence=match.match_confidence,
            signal_strength=score_result.signal_strength,
            recency_decay=score_result.recency_decay,
            icp_fit=score_result.icp_fit,
            score=score_result.score,
            signal_category=score_result.signal_category,
            reason=score_result.reason,
        )
        session.add(scored)
        await session.flush()

        if publisher is not None:
            slack_ts = await publisher.publish(scored, event, icp)
            if slack_ts:
                scored.published_at = datetime.now(timezone.utc)
                scored.slack_ts = slack_ts
                published += 1

        processed += 1

    log.info("pipeline.processed", processed=processed, published=published)
    return {"processed": processed, "published": published}
