from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signal_engine.db.models import IcpCompany, SignalEvent

log = structlog.get_logger(__name__)

MatchMethod = Literal["domain", "fuzzy_name", "unmatched"]


class MatchResult(BaseModel):
    icp_company_id: int | None
    match_method: MatchMethod
    match_confidence: float


class AccountMatcher:
    """Rules-based matcher. Domain exact-match first, then fuzzy name on aliases.

    Loaded once per pipeline run via from_session(); matching is pure-Python
    after that.
    """

    def __init__(self, icp_companies: list[IcpCompany], fuzzy_threshold: float = 0.85) -> None:
        self.icp_companies = icp_companies
        self.fuzzy_threshold = fuzzy_threshold
        self._by_id: dict[int, IcpCompany] = {c.id: c for c in icp_companies}
        self._by_domain: dict[str, IcpCompany] = {}
        for c in icp_companies:
            if c.domain:
                self._by_domain[c.domain.lower()] = c
            for alt in c.alt_domains or []:
                self._by_domain[alt.lower()] = c

    @classmethod
    async def from_session(
        cls, session: AsyncSession, fuzzy_threshold: float = 0.85
    ) -> AccountMatcher:
        result = await session.execute(select(IcpCompany).where(IcpCompany.active.is_(True)))
        return cls(list(result.scalars()), fuzzy_threshold=fuzzy_threshold)

    def get_icp(self, icp_id: int | None) -> IcpCompany | None:
        if icp_id is None:
            return None
        return self._by_id.get(icp_id)

    def match(self, event: SignalEvent) -> MatchResult:
        # 1. Exact domain match (primary + alt domains).
        if event.company_domain:
            hit = self._by_domain.get(event.company_domain.lower())
            if hit is not None:
                return MatchResult(
                    icp_company_id=hit.id, match_method="domain", match_confidence=1.0
                )

        # 2. Fuzzy name match against name + aliases.
        candidate_name = (event.normalized or {}).get("company_name")
        if candidate_name:
            best_id: int | None = None
            best_score = 0.0
            target = candidate_name.lower()
            for c in self.icp_companies:
                for alias in [c.name, *(c.aliases or [])]:
                    score = fuzz.token_set_ratio(target, alias.lower()) / 100.0
                    if score > best_score:
                        best_score = score
                        best_id = c.id
            if best_score >= self.fuzzy_threshold and best_id is not None:
                return MatchResult(
                    icp_company_id=best_id,
                    match_method="fuzzy_name",
                    match_confidence=round(best_score, 2),
                )

        return MatchResult(
            icp_company_id=None, match_method="unmatched", match_confidence=0.0
        )
