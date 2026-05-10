from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from signal_engine.db.models import SignalEvent, SourceRun
from signal_engine.dedupe import content_fingerprint, dedupe_key

log = structlog.get_logger(__name__)


class Observation(BaseModel):
    """One thing seen from a source. Concrete workers yield these from poll().

    `normalized` is the canonical extracted shape that goes into
    signal_events.normalized — keep it small and structured (role, jd_excerpt,
    location, company...). `raw` preserves the original payload.
    """

    source_event_id: str
    raw: dict[str, Any]
    normalized: dict[str, Any]
    company_domain: str | None = None
    company_name: str | None = None
    signal_type: str = "job_posting"
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def fingerprint(self) -> str:
        """Content hash used in the dedupe key.

        Override per source if you want to exclude noisy fields (e.g. a
        view-counter that changes every poll but doesn't represent a real edit).
        """
        return content_fingerprint(self.normalized)


class RunResult(BaseModel):
    source: str
    run_id: int | None
    status: str
    signals_seen: int
    signals_new: int
    error: str | None = None


class SourceWorker(ABC):
    """Template-method base for source workers.

    Concrete workers implement `poll()` as an async generator yielding
    Observations. The base class wraps every run in a `source_runs` heartbeat
    and handles dedupe + persistence — so every worker is canary-readable and
    failure-isolated without per-source bookkeeping.
    """

    name: ClassVar[str]

    @abstractmethod
    def poll(self) -> AsyncIterator[Observation]:
        """Yield Observations from the source. No DB writes inside poll()."""
        raise NotImplementedError

    async def run(self, session: AsyncSession) -> RunResult:
        run = SourceRun(source=self.name, status="running")
        session.add(run)
        await session.flush()
        run_id = run.id

        seen = 0
        new = 0
        error: str | None = None
        status = "ok"

        try:
            async for obs in self.poll():
                seen += 1
                key = dedupe_key(self.name, obs.source_event_id, obs.fingerprint())
                stmt = (
                    pg_insert(SignalEvent)
                    .values(
                        source=self.name,
                        source_event_id=obs.source_event_id,
                        dedupe_key=key,
                        observed_at=obs.observed_at,
                        raw=obs.raw,
                        normalized=obs.normalized,
                        company_domain=obs.company_domain,
                        signal_type=obs.signal_type,
                    )
                    .on_conflict_do_nothing(index_elements=["dedupe_key"])
                    .returning(SignalEvent.id)
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    new += 1
        except Exception as exc:  # noqa: BLE001 — base must catch to record run failure
            error = repr(exc)
            status = "failed"
            log.exception("source.run.failed", source=self.name)

        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.signals_seen = seen
        run.signals_new = new
        run.error = error

        return RunResult(
            source=self.name,
            run_id=run_id,
            status=status,
            signals_seen=seen,
            signals_new=new,
            error=error,
        )
