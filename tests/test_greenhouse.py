from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from signal_engine.sources.greenhouse import (
    GreenhouseCompany,
    GreenhouseWorker,
    _strip_html_content,
    load_companies,
    normalize_job,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_strip_html_content_decodes_and_strips_tags() -> None:
    raw = quote("<p>Help us <b>modernize</b> the stack.</p>")
    out = _strip_html_content(raw)
    assert "<" not in out
    assert ">" not in out
    assert "modernize" in out
    assert "Help us" in out


def test_strip_html_content_handles_empty() -> None:
    assert _strip_html_content(None) == ""
    assert _strip_html_content("") == ""


def test_normalize_job_extracts_canonical_fields() -> None:
    company = GreenhouseCompany(token="acme", name="Acme", domain="acme.com")
    job = {
        "id": 12345,
        "title": "Head of IT",
        "updated_at": "2026-05-01T12:00:00Z",
        "requisition_id": "REQ-1",
        "location": {"name": "San Francisco, CA"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "content": quote("<p>Help us modernize and add self-service automation.</p>"),
        "departments": [{"name": "IT"}],
    }
    out = normalize_job(job, company)
    assert out["role"] == "Head of IT"
    assert out["company_domain"] == "acme.com"
    assert out["location"] == "San Francisco, CA"
    assert out["department"] == "IT"
    assert "modernize" in out["jd_excerpt"]
    assert out["jd_length"] > 0


def test_load_companies_roundtrip(tmp_path: Path) -> None:
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "- token: acme\n  name: Acme\n  domain: acme.com\n  tier: tier_1\n"
    )
    companies = load_companies(seed)
    assert len(companies) == 1
    assert companies[0].token == "acme"
    assert companies[0].domain == "acme.com"


@pytest.mark.asyncio
async def test_worker_yields_observations_from_fixture() -> None:
    fixture_data = json.loads((FIXTURES / "greenhouse_sample.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/boards/acme/jobs"
        assert request.url.params.get("content") == "true"
        return httpx.Response(200, json=fixture_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        worker = GreenhouseWorker(
            companies=[GreenhouseCompany(token="acme", name="Acme", domain="acme.com")],
            client=client,
        )
        observations = [obs async for obs in worker.poll()]

    assert len(observations) == 2
    titles = {obs.normalized["role"] for obs in observations}
    assert titles == {"Head of IT", "ServiceNow Administrator"}
    assert all(obs.company_domain == "acme.com" for obs in observations)
    assert all(obs.signal_type == "job_posting" for obs in observations)
    # source_event_id is stringified greenhouse id
    assert {obs.source_event_id for obs in observations} == {"12345", "67890"}


@pytest.mark.asyncio
async def test_worker_skips_404_company_and_continues() -> None:
    """A missing board for one company must not break the rest of the run."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/boards/missing/" in str(request.url):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(
            200,
            json={"jobs": [{"id": 1, "title": "Admin", "content": ""}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        worker = GreenhouseWorker(
            companies=[
                GreenhouseCompany(token="missing", name="Gone"),
                GreenhouseCompany(token="acme", name="Acme", domain="acme.com"),
            ],
            client=client,
        )
        observations = [obs async for obs in worker.poll()]

    assert len(observations) == 1
    assert observations[0].source_event_id == "1"


@pytest.mark.asyncio
async def test_worker_continues_after_5xx_for_one_company() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/boards/broken/" in str(request.url):
            return httpx.Response(500, text="upstream error")
        return httpx.Response(200, json={"jobs": [{"id": 2, "title": "X", "content": ""}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        worker = GreenhouseWorker(
            companies=[
                GreenhouseCompany(token="broken", name="Broken"),
                GreenhouseCompany(token="acme", name="Acme"),
            ],
            client=client,
        )
        observations = [obs async for obs in worker.poll()]

    assert len(observations) == 1
    assert observations[0].source_event_id == "2"


def test_observation_fingerprint_changes_when_jd_changes() -> None:
    """Edited JD → new fingerprint → new dedupe_key → new signal_events row."""
    company = GreenhouseCompany(token="acme", name="Acme", domain="acme.com")
    job_v1 = {
        "id": 1,
        "title": "IT Manager",
        "content": quote("<p>We automate workflows.</p>"),
    }
    job_v2 = {
        "id": 1,
        "title": "IT Manager",
        "content": quote("<p>We automate workflows with AI.</p>"),
    }
    norm_v1 = normalize_job(job_v1, company)
    norm_v2 = normalize_job(job_v2, company)
    assert norm_v1 != norm_v2  # changes flow into the fingerprint
