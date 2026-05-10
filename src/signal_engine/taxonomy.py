"""Signal pattern taxonomy.

Patterns are data, not code, so adding an ICP signal is a config change rather
than a deploy. The scorer consumes DEFAULT_PATTERNS (or a YAML-loaded variant
in the future).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SignalCategory = Literal["churn", "buying", "pain"]


class PatternMatch(BaseModel):
    category: SignalCategory
    strength: float
    reason: str


class JobPostingPattern(BaseModel):
    name: str
    category: SignalCategory
    strength: float
    role_keywords: list[str] = []
    jd_keywords_any: list[str] = []
    jd_keywords_all: list[str] = []
    icp_tier_restriction: list[str] | None = None


DEFAULT_PATTERNS: list[JobPostingPattern] = [
    JobPostingPattern(
        name="competitor_admin_hire",
        category="churn",
        strength=0.9,
        role_keywords=["servicenow admin", "moveworks admin"],
        icp_tier_restriction=["competitor"],
    ),
    JobPostingPattern(
        name="it_leader_modernization",
        category="buying",
        strength=0.8,
        role_keywords=["head of it", "it manager", "director of it"],
        jd_keywords_any=["automate", "ai", "modernize", "self-service", "self service"],
        icp_tier_restriction=["tier_1", "tier_2", "tier_3"],
    ),
    JobPostingPattern(
        name="admin_pain_ticket_volume",
        category="pain",
        strength=0.7,
        role_keywords=["jamf admin", "okta admin", "slack admin"],
        jd_keywords_any=["ticket volume", "ticket backlog", "ticket queue", "overwhelmed"],
        icp_tier_restriction=["tier_1", "tier_2", "tier_3"],
    ),
]
