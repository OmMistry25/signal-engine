from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from signal_engine.db.models import IcpCompany, SignalEvent
from signal_engine.matcher.account_matcher import MatchResult
from signal_engine.scoring.scorer import (
    BASE_SIGNAL_STRENGTH,
    HALF_LIFE_DAYS,
    TIER_FIT,
    UNMATCHED_ICP_FIT,
    Scorer,
)

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)


def make_event(
    *,
    role: str = "",
    jd: str = "",
    company_name: str | None = None,
    observed_at: datetime | None = None,
) -> SignalEvent:
    normalized: dict[str, Any] = {"role": role, "jd_excerpt": jd}
    if company_name:
        normalized["company_name"] = company_name
    return SignalEvent(
        id=1,
        source="greenhouse",
        source_event_id="1",
        dedupe_key="k",
        raw={},
        normalized=normalized,
        company_domain="acme.com",
        signal_type="job_posting",
        observed_at=observed_at or NOW,
    )


def make_icp(name: str = "Acme", tier: str = "tier_1") -> IcpCompany:
    return IcpCompany(
        id=1, name=name, domain="acme.com", aliases=[], alt_domains=[], tier=tier, active=True
    )


def matched(icp_id: int = 1) -> MatchResult:
    return MatchResult(icp_company_id=icp_id, match_method="domain", match_confidence=1.0)


def unmatched() -> MatchResult:
    return MatchResult(icp_company_id=None, match_method="unmatched", match_confidence=0.0)


def test_buying_pattern_fires_on_it_leader_modernization() -> None:
    event = make_event(
        role="Head of IT",
        jd="We need someone to modernize our stack and add ai automation.",
    )
    icp = make_icp(tier="tier_1")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.signal_category == "buying"
    assert result.pattern_name == "it_leader_modernization"
    assert result.signal_strength == 0.8
    assert result.icp_fit == TIER_FIT["tier_1"]
    assert result.recency_decay == 1.0
    assert result.score == 80.0


def test_churn_pattern_fires_for_competitor_admin_hire() -> None:
    event = make_event(role="Senior ServiceNow Admin", jd="manage our service desk")
    icp = make_icp(name="ServiceNow", tier="competitor")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.signal_category == "churn"
    assert result.pattern_name == "competitor_admin_hire"
    # 0.9 strength × 0.8 competitor fit × 1.0 recency × 100 = 72.0
    assert result.score == 72.0


def test_pain_pattern_fires_on_ticket_volume_language() -> None:
    event = make_event(
        role="Jamf Admin",
        jd="You'll own our jamf platform and reduce ticket volume across the org.",
    )
    icp = make_icp(tier="tier_2")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.signal_category == "pain"
    assert result.pattern_name == "admin_pain_ticket_volume"


def test_no_pattern_fires_uses_base_strength_and_other_category() -> None:
    event = make_event(role="Software Engineer", jd="we use python")
    icp = make_icp(tier="tier_1")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.signal_category == "other"
    assert result.pattern_name is None
    assert result.signal_strength == BASE_SIGNAL_STRENGTH


def test_unmatched_icp_drags_score_down() -> None:
    event = make_event(
        role="Head of IT",
        jd="modernize our stack and add ai automation",
    )
    # Same buying pattern would fire — but pattern is tier-restricted to tier_*, so unmatched skips it.
    result = Scorer(now=NOW).score(event, unmatched(), None)
    assert result.signal_category == "other"  # pattern didn't fire due to tier restriction
    assert result.icp_fit == UNMATCHED_ICP_FIT
    assert "no ICP match" in result.reason


def test_recency_decay_halves_at_half_life() -> None:
    event = make_event(
        role="Head of IT",
        jd="modernize",
        observed_at=NOW - timedelta(days=HALF_LIFE_DAYS),
    )
    icp = make_icp(tier="tier_1")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.recency_decay == 0.5


def test_future_observed_at_is_clamped_to_fresh() -> None:
    event = make_event(role="x", jd="y", observed_at=NOW + timedelta(days=5))
    icp = make_icp(tier="tier_1")
    result = Scorer(now=NOW).score(event, matched(), icp)
    assert result.recency_decay == 1.0


def test_competitor_tier_restriction_keeps_buying_from_firing() -> None:
    """A 'buying' pattern restricted to tier_* shouldn't fire on competitors."""
    event = make_event(role="Head of IT", jd="modernize automate")
    competitor = make_icp(name="ServiceNow", tier="competitor")
    result = Scorer(now=NOW).score(event, matched(), competitor)
    # No pattern restricted to competitor matches "head of it" → "other"
    assert result.pattern_name != "it_leader_modernization"


def test_reason_string_includes_components_for_debugging() -> None:
    event = make_event(role="Head of IT", jd="modernize")
    icp = make_icp(tier="tier_1")
    reason = Scorer(now=NOW).score(event, matched(), icp).reason
    assert "strength" in reason and "recency" in reason and "fit" in reason
    assert "tier_1" in reason
