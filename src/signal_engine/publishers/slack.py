from __future__ import annotations

from typing import Any, Protocol

import structlog

from signal_engine.config import get_settings
from signal_engine.db.models import IcpCompany, ScoredSignal, SignalEvent

log = structlog.get_logger(__name__)

CATEGORY_EMOJI: dict[str, str] = {
    "churn": ":rotating_light:",
    "buying": ":money_with_wings:",
    "pain": ":fire:",
    "other": ":memo:",
}


class SlackPostable(Protocol):
    """Subset of slack_sdk.web.async_client.AsyncWebClient used by SlackPublisher.

    Tests can satisfy this without subclassing AsyncWebClient.
    """

    async def chat_postMessage(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]],
    ) -> Any: ...


class SlackPublisher:
    def __init__(self, client: SlackPostable, channel: str, threshold: float = 60.0) -> None:
        self.client = client
        self.channel = channel
        self.threshold = threshold

    @classmethod
    def from_settings(cls) -> SlackPublisher | None:
        """Build a real publisher from env, or None if Slack isn't configured.

        Returning None lets the pipeline run in dry mode locally without erroring.
        """
        settings = get_settings()
        if not settings.slack_bot_token or not settings.slack_channel_id:
            log.info("slack.disabled", reason="missing token or channel")
            return None
        # Local import so the rest of the module doesn't need slack_sdk available
        # for tests / dry runs.
        from slack_sdk.web.async_client import AsyncWebClient

        return cls(
            client=AsyncWebClient(token=settings.slack_bot_token),
            channel=settings.slack_channel_id,
            threshold=settings.score_publish_threshold,
        )

    async def publish(
        self,
        scored: ScoredSignal,
        event: SignalEvent,
        icp: IcpCompany | None,
    ) -> str | None:
        """Post if score >= threshold. Returns the Slack message ts, or None."""
        if float(scored.score) < self.threshold:
            return None

        blocks = format_blocks(scored, event, icp)
        text = fallback_text(scored, event, icp)
        try:
            response = await self.client.chat_postMessage(
                channel=self.channel, text=text, blocks=blocks
            )
        except Exception as exc:  # noqa: BLE001 — never let slack errors crash the pipeline
            log.warning("slack.post_failed", error=repr(exc), score=float(scored.score))
            return None
        ts = response["ts"] if hasattr(response, "__getitem__") else None
        return ts if isinstance(ts, str) else None


def fallback_text(scored: ScoredSignal, event: SignalEvent, icp: IcpCompany | None) -> str:
    """Plain-text fallback for Slack clients that don't render blocks."""
    company = icp.name if icp else (event.normalized.get("company_name") or "unmatched")
    role = (event.normalized or {}).get("role", "?")
    return f"{scored.signal_category} signal (score {float(scored.score):g}) — {role} @ {company}"


def format_blocks(
    scored: ScoredSignal, event: SignalEvent, icp: IcpCompany | None
) -> list[dict[str, Any]]:
    normalized = event.normalized or {}
    company = icp.name if icp else (normalized.get("company_name") or "_unmatched_")
    tier = f" ({icp.tier})" if icp else " (no ICP match)"
    role = normalized.get("role", "?")
    location = normalized.get("location") or "—"
    jd = normalized.get("jd_excerpt") or ""
    jd_preview = jd[:280] + ("…" if len(jd) > 280 else "")
    url = normalized.get("absolute_url")
    emoji = CATEGORY_EMOJI.get(str(scored.signal_category), ":memo:")

    header_text = (
        f"{emoji} *{scored.signal_category.upper()} signal*  ·  score *{float(scored.score):g}*"
    )
    body_text = (
        f"*{role}* @ *{company}*{tier}\n"
        f":round_pushpin: {location}\n"
    )
    if jd_preview:
        body_text += f"> {jd_preview}\n"
    if url:
        body_text += f":link: <{url}|view posting>\n"
    body_text += f":bookmark_tabs: {scored.reason}"

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body_text}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"source: `{event.source}` · event #{event.id} · :+1: / :-1: to label"}
        ]},
    ]
