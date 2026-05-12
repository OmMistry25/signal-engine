from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from signal_engine.db.models import IcpCompany, SignalEvent
from signal_engine.matcher.account_matcher import MatchResult
from signal_engine.taxonomy import DEFAULT_PATTERNS, JobPostingPattern, SignalCategory

TIER_FIT: dict[str, float] = {
    "tier_1": 1.0,
    "tier_2": 0.7,
    "tier_3": 0.5,
    "competitor": 0.8,
}
UNMATCHED_ICP_FIT = 0.2
BASE_SIGNAL_STRENGTH = 0.3
HALF_LIFE_DAYS = 14.0


class ScoreResult(BaseModel):
    signal_strength: float
    recency_decay: float
    icp_fit: float
    score: float
    signal_category: SignalCategory | str  # "other" if no pattern fires
    reason: str
    pattern_name: str | None = None


class Scorer:
    """Rules-based scorer: signal_strength × recency_decay × icp_fit × 100.

    Patterns come from the taxonomy module (data, not code). Adding a new
    pattern is a one-line change to DEFAULT_PATTERNS.
    """

    def __init__(
        self,
        patterns: list[JobPostingPattern] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.patterns = patterns if patterns is not None else DEFAULT_PATTERNS
        self._now = now  # injectable for deterministic tests

    def _current_time(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    def score(
        self, event: SignalEvent, match: MatchResult, icp: IcpCompany | None
    ) -> ScoreResult:
        firing = self._find_firing_pattern(event, icp)
        if firing is not None:
            signal_strength = firing.strength
            category: SignalCategory | str = firing.category
            pattern_name: str | None = firing.name
            reasons = [f"pattern '{firing.name}' fired"]
        else:
            signal_strength = BASE_SIGNAL_STRENGTH
            category = "other"
            pattern_name = None
            reasons = ["no taxonomy pattern fired"]

        recency_decay = self._recency_decay(event.observed_at)

        if icp is None:
            icp_fit = UNMATCHED_ICP_FIT
            reasons.append("no ICP match")
        else:
            icp_fit = TIER_FIT.get(icp.tier, 0.5)
            reasons.append(f"{icp.tier} ICP ({icp.name})")

        score = signal_strength * recency_decay * icp_fit * 100.0
        reasons.append(
            f"strength {signal_strength:.2f} × recency {recency_decay:.2f} × fit {icp_fit:.2f}"
        )

        return ScoreResult(
            signal_strength=round(signal_strength, 2),
            recency_decay=round(recency_decay, 2),
            icp_fit=round(icp_fit, 2),
            score=round(score, 2),
            signal_category=category,
            reason="; ".join(reasons),
            pattern_name=pattern_name,
        )

    def _recency_decay(self, observed_at: datetime) -> float:
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (self._current_time() - observed_at).total_seconds() / 86400.0)
        decay = 2 ** (-age_days / HALF_LIFE_DAYS)
        return max(0.0, min(1.0, decay))

    def _find_firing_pattern(
        self, event: SignalEvent, icp: IcpCompany | None
    ) -> JobPostingPattern | None:
        normalized = event.normalized or {}
        role = (normalized.get("role") or "").lower()
        jd = (normalized.get("jd_excerpt") or "").lower()

        firing: list[JobPostingPattern] = []
        for p in self.patterns:
            if p.icp_tier_restriction is not None:
                if icp is None or icp.tier not in p.icp_tier_restriction:
                    continue
            if p.role_keywords and not any(kw in role for kw in p.role_keywords):
                continue
            if p.jd_keywords_any and not any(kw in jd for kw in p.jd_keywords_any):
                continue
            if p.jd_keywords_all and not all(kw in jd for kw in p.jd_keywords_all):
                continue
            firing.append(p)

        if not firing:
            return None
        return max(firing, key=lambda p: p.strength)
