# signal-engine

Real-time intent signal capture for console GTM. Polls owned sources (job boards, SEC filings, etc.), normalizes to a canonical shape, scores against an ICP list, and posts high-score signals to Slack for SDRs to action manually.

V1 is **capture-only** — no outbound automation. Validate signal → meeting conversion with humans in the loop first.

## Architecture

```
[sources] → [normalizers] → [signal_events (append-only)]
   → [account_matcher] → [scored_signals] → [slack #gtm-signals-live]
```

- One source worker per origin (greenhouse, lever, ...). Workers are isolated failure domains.
- `signal_events` is append-only — edited postings produce new rows so the history is preserved (a re-opened req is itself a signal).
- Matcher is rules-based first (domain → fuzzy name); LLM only after rules cap out.
- Canary posts per-source health into the same Slack channel.

## Quickstart

```bash
uv sync
cp .env.example .env  # fill DATABASE_URL, SLACK_*
uv run alembic upgrade head
uv run signal-engine version
```

## Layout

```
src/signal_engine/
  config.py          # pydantic settings
  dedupe.py          # shared dedupe-key generation
  taxonomy.py        # ICP signal patterns (data, not code)
  cli.py             # `signal-engine ...`
  db/models.py       # SQLAlchemy 2.0 models for the 5 tables
  db/session.py      # async engine + session factory
  sources/base.py    # SourceWorker ABC (poll → normalize → persist)
  sources/greenhouse.py  # (next PR)
  matcher/           # domain → fuzzy → llm    (next PR)
  scoring/           # signal_strength × recency × icp_fit  (next PR)
  publishers/slack.py    # (next PR)
  monitor/canary.py      # (next PR)
tests/
alembic/
```

## Adding a new source

Subclass `SourceWorker` and implement `poll()`. The base class handles dedupe, persistence, and the `source_runs` heartbeat — canary picks up worker health for free.

```python
class MySource(SourceWorker):
    name = "my_source"

    async def poll(self):
        async for raw in fetch_things():
            yield Observation(
                source_event_id=raw["id"],
                raw=raw,
                normalized={"role": raw["title"], "company": raw["company"], ...},
                company_domain=raw.get("domain"),
            )
```

## Schema

Five tables, all in the initial migration:

| Table | Purpose |
|---|---|
| `signal_events` | Append-only log of every observation. `dedupe_key` includes a content fingerprint so edited postings produce new rows. |
| `scored_signals` | Account-matched + scored output. One row per scoring run per event; latest wins for display. |
| `icp_companies` | Sell-to and competitor-watch list with domains, aliases, alt-domains for fuzzy matching. |
| `manual_overrides` | Discriminated union (`kind = 'feedback' | 'rule'`) for SDR thumbs-up/down and suppress/boost rules. |
| `source_runs` | Per-poll heartbeat. Canary reads this to distinguish "source broken" from "no signals seen". |
