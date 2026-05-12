from __future__ import annotations

import urllib.parse
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

import httpx
import structlog
import yaml
from pydantic import BaseModel
from selectolax.parser import HTMLParser

from signal_engine.sources.base import Observation, SourceWorker

log = structlog.get_logger(__name__)

BOARDS_API_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


class GreenhouseCompany(BaseModel):
    token: str            # greenhouse board slug, e.g. "airbnb"
    name: str
    domain: str | None = None
    tier: str | None = None


def load_companies(path: Path | str) -> list[GreenhouseCompany]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return [GreenhouseCompany.model_validate(item) for item in raw]


def _strip_html_content(raw_content: str | None) -> str:
    """Greenhouse returns `content` as percent-encoded HTML — decode then strip tags."""
    if not raw_content:
        return ""
    decoded = urllib.parse.unquote(raw_content)
    return HTMLParser(decoded).text(separator=" ", strip=True)


def _location_name(job: dict[str, Any]) -> str | None:
    location = job.get("location")
    if isinstance(location, dict):
        return location.get("name")
    return None


def _department_name(job: dict[str, Any]) -> str | None:
    departments = job.get("departments")
    if isinstance(departments, list) and departments:
        first = departments[0]
        if isinstance(first, dict):
            return first.get("name")
    return None


def normalize_job(job: dict[str, Any], company: GreenhouseCompany) -> dict[str, Any]:
    jd_text = _strip_html_content(job.get("content"))
    return {
        "company_name": company.name,
        "company_domain": company.domain,
        "role": (job.get("title") or "").strip(),
        "location": _location_name(job),
        "department": _department_name(job),
        "absolute_url": job.get("absolute_url"),
        "updated_at": job.get("updated_at"),
        "requisition_id": job.get("requisition_id"),
        "jd_excerpt": jd_text[:2000],
        "jd_length": len(jd_text),
    }


class GreenhouseWorker(SourceWorker):
    name: ClassVar[str] = "greenhouse"

    def __init__(
        self,
        companies: list[GreenhouseCompany],
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.companies = companies
        self._injected_client = client
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)

    async def poll(self) -> AsyncIterator[Observation]:
        if self._injected_client is not None:
            async for obs in self._poll_all(self._injected_client):
                yield obs
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async for obs in self._poll_all(client):
                yield obs

    async def _poll_all(self, client: httpx.AsyncClient) -> AsyncIterator[Observation]:
        for company in self.companies:
            try:
                async for obs in self._poll_company(client, company):
                    yield obs
            except httpx.HTTPError as exc:
                log.warning(
                    "greenhouse.company_failed",
                    token=company.token,
                    error=repr(exc),
                )
                continue

    async def _poll_company(
        self, client: httpx.AsyncClient, company: GreenhouseCompany
    ) -> AsyncIterator[Observation]:
        url = BOARDS_API_URL.format(token=company.token)
        resp = await client.get(url, params={"content": "true"})
        if resp.status_code == 404:
            log.warning("greenhouse.board_not_found", token=company.token)
            return
        resp.raise_for_status()
        data = resp.json()
        for job in data.get("jobs", []):
            if "id" not in job:
                continue
            yield Observation(
                source_event_id=str(job["id"]),
                raw=job,
                normalized=normalize_job(job, company),
                company_domain=company.domain,
                company_name=company.name,
                signal_type="job_posting",
            )
