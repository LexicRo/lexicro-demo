from app.session import Session, issue, parse

SECRET = "test-secret"
MAX_AGE = 3600.0


def test_roundtrip_preserves_sid_and_lang():
    raw = issue(SECRET, "ro", now=1000.0)
    s = parse(SECRET, raw, now=1000.0, max_age=MAX_AGE)
    assert isinstance(s, Session)
    assert s.lang == "ro"
    assert s.sid


def test_two_issues_get_different_sids():
    a = parse(SECRET, issue(SECRET, "en", now=1000.0), now=1000.0, max_age=MAX_AGE)
    b = parse(SECRET, issue(SECRET, "en", now=1000.0), now=1000.0, max_age=MAX_AGE)
    assert a.sid != b.sid


def test_tampered_payload_is_rejected():
    raw = issue(SECRET, "en", now=1000.0)
    payload, _, sig = raw.rpartition(".")
    flipped = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    assert parse(SECRET, flipped + "." + sig, now=1000.0, max_age=MAX_AGE) is None


def test_wrong_secret_is_rejected():
    raw = issue(SECRET, "en", now=1000.0)
    assert parse("other-secret", raw, now=1000.0, max_age=MAX_AGE) is None


def test_expired_cookie_is_rejected():
    raw = issue(SECRET, "en", now=1000.0)
    assert parse(SECRET, raw, now=1000.0 + MAX_AGE + 1, max_age=MAX_AGE) is None


def test_missing_or_garbage_cookie_is_rejected():
    assert parse(SECRET, None, now=1000.0, max_age=MAX_AGE) is None
    assert parse(SECRET, "", now=1000.0, max_age=MAX_AGE) is None
    assert parse(SECRET, "not-a-cookie", now=1000.0, max_age=MAX_AGE) is None
    assert parse(SECRET, "a.b.c", now=1000.0, max_age=MAX_AGE) is None


def test_unknown_language_falls_back_to_en():
    raw = issue(SECRET, "de", now=1000.0)
    assert parse(SECRET, raw, now=1000.0, max_age=MAX_AGE).lang == "en"


def test_sid_survives_a_language_change():
    first = parse(SECRET, issue(SECRET, "en", now=1000.0), now=1000.0, max_age=MAX_AGE)
    raw = issue(SECRET, "ro", now=1001.0, sid=first.sid)
    second = parse(SECRET, raw, now=1001.0, max_age=MAX_AGE)
    assert second.sid == first.sid
    assert second.lang == "ro"


def test_theme_roundtrips_and_defaults_to_auto():
    s = parse(SECRET, issue(SECRET, "en", now=1000.0, theme="dark"), now=1000.0, max_age=MAX_AGE)
    assert s.theme == "dark"
    # no theme supplied, and an unrecognised one, both mean "follow the system"
    assert parse(SECRET, issue(SECRET, "en", now=1000.0), now=1000.0, max_age=MAX_AGE).theme == "auto"
    assert parse(
        SECRET, issue(SECRET, "en", now=1000.0, theme="neon"), now=1000.0, max_age=MAX_AGE
    ).theme == "auto"


def test_theme_and_sid_survive_each_other():
    """Changing theme must not mint a fresh sid -- that would hand the visitor a
    new throttle budget on every click of the appearance control."""
    first = parse(SECRET, issue(SECRET, "en", now=1000.0, theme="dark"), now=1000.0, max_age=MAX_AGE)
    second = parse(
        SECRET,
        issue(SECRET, "ro", now=1001.0, sid=first.sid, theme=first.theme),
        now=1001.0, max_age=MAX_AGE,
    )
    assert second.sid == first.sid
    assert second.theme == "dark"
    assert second.lang == "ro"
