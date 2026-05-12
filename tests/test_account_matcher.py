from __future__ import annotations

from typing import Any

from signal_engine.db.models import IcpCompany, SignalEvent
from signal_engine.matcher.account_matcher import AccountMatcher


def make_icp(
    *,
    id: int,
    name: str,
    domain: str | None = None,
    aliases: list[str] | None = None,
    alt_domains: list[str] | None = None,
    tier: str = "tier_2",
) -> IcpCompany:
    c = IcpCompany(
        id=id,
        name=name,
        domain=domain,
        aliases=aliases or [],
        alt_domains=alt_domains or [],
        tier=tier,
        active=True,
    )
    return c


def make_event(
    *,
    company_domain: str | None = None,
    company_name: str | None = None,
    normalized: dict[str, Any] | None = None,
) -> SignalEvent:
    norm: dict[str, Any] = dict(normalized or {})
    if company_name and "company_name" not in norm:
        norm["company_name"] = company_name
    return SignalEvent(
        id=1,
        source="greenhouse",
        source_event_id="123",
        dedupe_key="greenhouse:123:abc",
        raw={},
        normalized=norm,
        company_domain=company_domain,
        signal_type="job_posting",
    )


def test_domain_match_is_exact_and_full_confidence() -> None:
    icp = make_icp(id=1, name="Acme", domain="acme.com", tier="tier_1")
    matcher = AccountMatcher([icp])

    result = matcher.match(make_event(company_domain="acme.com", company_name="Acme Co"))
    assert result.match_method == "domain"
    assert result.icp_company_id == 1
    assert result.match_confidence == 1.0


def test_domain_match_uses_alt_domains() -> None:
    icp = make_icp(
        id=2, name="Acme", domain="acme.com", alt_domains=["acme.io", "acmecorp.com"]
    )
    matcher = AccountMatcher([icp])
    result = matcher.match(make_event(company_domain="acmecorp.com"))
    assert result.icp_company_id == 2
    assert result.match_method == "domain"


def test_domain_match_is_case_insensitive() -> None:
    icp = make_icp(id=3, name="Acme", domain="acme.com")
    matcher = AccountMatcher([icp])
    result = matcher.match(make_event(company_domain="ACME.com"))
    assert result.match_method == "domain"


def test_fuzzy_name_match_falls_back_when_no_domain() -> None:
    icp = make_icp(id=4, name="Stripe Inc", aliases=["Stripe"])
    matcher = AccountMatcher([icp])
    result = matcher.match(make_event(company_name="Stripe, Inc."))
    assert result.match_method == "fuzzy_name"
    assert result.icp_company_id == 4
    assert result.match_confidence >= 0.85


def test_fuzzy_name_below_threshold_is_unmatched() -> None:
    icp = make_icp(id=5, name="Stripe")
    matcher = AccountMatcher([icp], fuzzy_threshold=0.9)
    result = matcher.match(make_event(company_name="Completely Different Co"))
    assert result.match_method == "unmatched"
    assert result.icp_company_id is None
    assert result.match_confidence == 0.0


def test_domain_match_preferred_over_fuzzy_when_both_available() -> None:
    acme = make_icp(id=1, name="Acme")
    stripe = make_icp(id=2, name="Stripe", domain="stripe.com")
    matcher = AccountMatcher([acme, stripe])
    # event has stripe domain but acme-ish name — domain wins
    result = matcher.match(make_event(company_domain="stripe.com", company_name="Acmee"))
    assert result.icp_company_id == 2
    assert result.match_method == "domain"


def test_unmatched_when_no_domain_and_no_name() -> None:
    matcher = AccountMatcher([make_icp(id=1, name="Acme", domain="acme.com")])
    result = matcher.match(make_event())
    assert result.match_method == "unmatched"


def test_get_icp_returns_company_or_none() -> None:
    icp = make_icp(id=7, name="Acme")
    matcher = AccountMatcher([icp])
    assert matcher.get_icp(7) is icp
    assert matcher.get_icp(None) is None
    assert matcher.get_icp(999) is None
