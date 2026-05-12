from __future__ import annotations

from typing import Any

import pytest

from signal_engine.db.models import IcpCompany, ScoredSignal, SignalEvent
from signal_engine.publishers.slack import SlackPublisher, format_blocks


class FakeSlack:
    def __init__(self, raise_on_post: bool = False) -> None:
        self.posts: list[dict[str, Any]] = []
        self.raise_on_post = raise_on_post

    async def chat_postMessage(
        self, *, channel: str, text: str, blocks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if self.raise_on_post:
            raise RuntimeError("slack is down")
        self.posts.append({"channel": channel, "text": text, "blocks": blocks})
        return {"ts": f"1700000000.{len(self.posts):06d}"}


def make_event() -> SignalEvent:
    return SignalEvent(
        id=42,
        source="greenhouse",
        source_event_id="123",
        dedupe_key="k",
        raw={},
        normalized={
            "company_name": "Acme",
            "role": "Head of IT",
            "location": "San Francisco, CA",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "jd_excerpt": "Help us modernize and add self-service automation.",
        },
        company_domain="acme.com",
        signal_type="job_posting",
    )


def make_scored(score: float = 80.0, category: str = "buying") -> ScoredSignal:
    return ScoredSignal(
        id=1,
        signal_event_id=42,
        icp_company_id=1,
        match_method="domain",
        match_confidence=1.0,
        signal_strength=0.8,
        recency_decay=1.0,
        icp_fit=1.0,
        score=score,
        signal_category=category,
        reason="pattern 'it_leader_modernization' fired; tier_1 ICP (Acme)",
    )


def make_icp() -> IcpCompany:
    return IcpCompany(
        id=1,
        name="Acme",
        domain="acme.com",
        aliases=[],
        alt_domains=[],
        tier="tier_1",
        active=True,
    )


@pytest.mark.asyncio
async def test_publish_above_threshold_posts_and_returns_ts() -> None:
    fake = FakeSlack()
    pub = SlackPublisher(client=fake, channel="C-test", threshold=60.0)

    ts = await pub.publish(make_scored(score=85.0), make_event(), make_icp())

    assert ts is not None
    assert len(fake.posts) == 1
    posted = fake.posts[0]
    assert posted["channel"] == "C-test"
    assert "Head of IT" in posted["text"]


@pytest.mark.asyncio
async def test_publish_below_threshold_skips_post() -> None:
    fake = FakeSlack()
    pub = SlackPublisher(client=fake, channel="C-test", threshold=60.0)

    ts = await pub.publish(make_scored(score=45.0), make_event(), make_icp())

    assert ts is None
    assert fake.posts == []


@pytest.mark.asyncio
async def test_publish_swallows_slack_errors_and_returns_none() -> None:
    """Slack outage must not crash the pipeline — the scored row was already saved."""
    fake = FakeSlack(raise_on_post=True)
    pub = SlackPublisher(client=fake, channel="C-test", threshold=60.0)

    ts = await pub.publish(make_scored(score=85.0), make_event(), make_icp())
    assert ts is None


def test_format_blocks_shows_company_role_score_and_url() -> None:
    blocks = format_blocks(make_scored(), make_event(), make_icp())
    rendered = " ".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "Head of IT" in rendered
    assert "Acme" in rendered
    assert "tier_1" in rendered
    assert "BUYING" in rendered
    assert "boards.greenhouse.io/acme/jobs/123" in rendered


def test_format_blocks_handles_unmatched_icp() -> None:
    blocks = format_blocks(
        make_scored(category="other", score=50.0), make_event(), icp=None
    )
    rendered = " ".join(
        b["text"]["text"] for b in blocks if b["type"] == "section"
    )
    assert "no ICP match" in rendered


def test_format_blocks_truncates_long_jd() -> None:
    event = make_event()
    event.normalized = {**event.normalized, "jd_excerpt": "x" * 500}
    blocks = format_blocks(make_scored(), event, make_icp())
    body = next(b["text"]["text"] for b in blocks if b["type"] == "section" and "round_pushpin" in b["text"]["text"])
    assert "…" in body
