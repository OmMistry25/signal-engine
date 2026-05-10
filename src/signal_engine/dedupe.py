from __future__ import annotations

import hashlib
import json
from typing import Any


def content_fingerprint(content: dict[str, Any] | str) -> str:
    """Stable 16-char hash of meaningful content.

    A dict is serialized with sorted keys so attribute order doesn't affect the hash.
    The hash changes only when the content meaningfully changes — which is what we
    want for an edited job posting to produce a new signal_events row.
    """
    if isinstance(content, dict):
        payload = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        payload = content
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dedupe_key(source: str, source_event_id: str, fingerprint: str) -> str:
    """Compose the dedupe key stored on signal_events.

    Edits to a posting yield a new fingerprint → new key → new row in the
    append-only log.
    """
    return f"{source}:{source_event_id}:{fingerprint}"
