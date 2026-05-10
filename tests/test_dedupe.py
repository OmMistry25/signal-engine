from signal_engine.dedupe import content_fingerprint, dedupe_key


def test_fingerprint_stable_across_key_order() -> None:
    a = content_fingerprint({"role": "IT manager", "company": "Acme"})
    b = content_fingerprint({"company": "Acme", "role": "IT manager"})
    assert a == b


def test_fingerprint_changes_when_content_changes() -> None:
    a = content_fingerprint({"role": "IT manager", "jd": "we automate things"})
    b = content_fingerprint({"role": "IT manager", "jd": "we automate everything"})
    assert a != b


def test_dedupe_key_format() -> None:
    assert dedupe_key("greenhouse", "job-123", "abc123") == "greenhouse:job-123:abc123"


def test_edited_posting_produces_new_dedupe_key() -> None:
    """Append-only: same source + event id with edited content → new row."""
    fp1 = content_fingerprint({"jd": "v1"})
    fp2 = content_fingerprint({"jd": "v2"})
    assert dedupe_key("greenhouse", "job-1", fp1) != dedupe_key("greenhouse", "job-1", fp2)
