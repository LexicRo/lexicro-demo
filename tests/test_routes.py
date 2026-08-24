import asyncio
import logging

from fastapi.testclient import TestClient

from app.session import COOKIE_NAME, parse
from app.strings import STRINGS
from tests.conftest import HERO_A, SETTINGS


def test_index_renders_and_sets_a_cookie(client):
    r = client.get("/")
    assert r.status_code == 200
    assert COOKIE_NAME in r.cookies


def test_index_never_contains_the_api_key(client):
    """The single most important test in this repo -- checked on every kind
    of response the app produces, not just the GET / happy path: a 403
    (no session), a 400 (over the character cap), /healthz, and a 404."""
    responses = [
        client.post("/api/analyze", json={"text": "x"}),          # 403, no cookie yet
        client.get("/"),                                          # 200
        client.post("/api/analyze", json={"text": "a" * 501}),    # 400, over the cap
        client.get("/healthz"),                                   # healthz
        client.get("/this-route-does-not-exist"),                 # 404
    ]
    assert [r.status_code for r in responses] == [403, 200, 400, 200, 404]
    for r in responses:
        assert SETTINGS.api_key not in r.text
        for value in r.headers.values():
            assert SETTINGS.api_key not in value


def test_hero_text_is_served_without_touching_upstream(client, upstream):
    client.get("/")
    r = client.post("/api/analyze", json={"text": HERO_A})
    assert r.status_code == 200
    assert r.json()["sentences"] == ["cached-a"]
    assert upstream.calls == 0


def test_hero_hit_does_not_consume_throttle_budget(client, upstream):
    client.get("/")
    for _ in range(50):
        assert client.post("/api/analyze", json={"text": HERO_A}).status_code == 200
    r = client.post("/api/analyze", json={"text": "Un text nou."})
    assert r.status_code == 200
    assert upstream.calls == 1


def test_non_hero_text_reaches_upstream(client, upstream):
    client.get("/")
    r = client.post("/api/analyze", json={"text": "Un text oarecare."})
    assert r.status_code == 200
    assert upstream.calls == 1


def test_request_without_a_cookie_is_refused(client, upstream):
    r = client.post("/api/analyze", json={"text": "Un text oarecare."})
    assert r.status_code == 403
    assert upstream.calls == 0


def test_text_over_the_cap_is_refused_before_upstream(client, upstream):
    client.get("/")
    r = client.post("/api/analyze", json={"text": "a" * 501})
    assert r.status_code == 400
    assert upstream.calls == 0


def test_text_at_the_cap_is_accepted(client):
    client.get("/")
    assert client.post("/api/analyze", json={"text": "a" * 500}).status_code == 200


def test_throttle_refusal_returns_429_and_a_cta(client):
    client.get("/")
    for _ in range(20):
        client.post("/api/analyze", json={"text": "Text unic numarul " + str(_)})
    r = client.post("/api/analyze", json={"text": "Inca unul."})
    assert r.status_code == 429
    assert r.json() == {"error": STRINGS["en"]["err_throttled"]}


def test_language_switch_preserves_the_session_id(client, clock):
    """Must prove the sid itself survives the switch, not just that the
    cookie string changed -- an implementation that mints a fresh sid on
    every ?lang= switch would also make `before != after` true, while
    silently handing every visitor a one-click throttle reset."""
    client.get("/")
    before = client.cookies[COOKIE_NAME]
    client.get("/?lang=ro")
    after = client.cookies[COOKIE_NAME]
    assert before != after  # re-signed

    before_session = parse(SETTINGS.session_secret, before, clock(), SETTINGS.session_max_age_s)
    after_session = parse(SETTINGS.session_secret, after, clock(), SETTINGS.session_max_age_s)
    assert before_session is not None
    assert after_session is not None
    assert before_session.sid == after_session.sid
    assert before_session.lang == "en"
    assert after_session.lang == "ro"

    r = client.get("/")
    assert r.status_code == 200


def test_romanian_page_renders_romanian_copy(client):
    from app.strings import STRINGS
    r = client.get("/?lang=ro")
    assert STRINGS["ro"]["submit"] in r.text


def test_healthz_reports_ok_when_versions_match(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["fixture_model_version"] == "phase2-baseline-0.1"
    assert body["version_drift"] is False


def test_healthz_returns_503_when_the_model_moves(client, upstream):
    """The hero fixture is stale against a newer upstream model_version --
    persistent and actionable (someone must regenerate the fixture) -- so
    this is the one reason worth paging a monitor over. A plain 200 body
    field would never trip an UptimeRobot-class HTTP monitor."""
    import httpx

    def drifted(request):
        upstream.calls += 1
        return httpx.Response(200, json={"model_version": "phase3-different"})

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(drifted))
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["live_model_version"] == "phase3-different"
    assert body["version_drift"] is True


def test_head_healthz_returns_200_in_the_normal_case(client):
    """UptimeRobot-class monitors default to HEAD. FastAPI's @app.get() only
    wires up GET (unlike Starlette's bare Route), so this must be exercised
    explicitly rather than assumed to piggyback on the GET test above."""
    r = client.head("/healthz")
    assert r.status_code == 200
    assert r.text == ""


def test_head_healthz_returns_503_on_drift(client, upstream):
    """The status code is the entire signal a HEAD-only monitor gets -- it
    never sees the body -- so drift must still flip it to 503 over HEAD."""
    import httpx

    def drifted(request):
        upstream.calls += 1
        return httpx.Response(200, json={"model_version": "phase3-different"})

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(drifted))
    r = client.head("/healthz")
    assert r.status_code == 503
    assert r.text == ""


def test_head_index_returns_200(client):
    """A public web page answering 405 to HEAD is wrong regardless of
    /healthz -- a monitor could be pointed at either."""
    r = client.head("/")
    assert r.status_code == 200


def test_healthz_stays_200_when_upstream_is_unreachable(client):
    """Transient upstream trouble is not this service's outage -- the
    upstream API has its own monitoring -- so it must not page."""
    import httpx

    def unreachable(request):
        raise httpx.ConnectError("boom", request=request)

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(unreachable))
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["reason"] == "upstream unreachable"
    assert body["version_drift"] is False


def test_healthz_stays_200_when_upstream_shape_is_unreadable(client):
    """We cannot read a version out of a non-dict response, so we don't know
    whether we've drifted -- a 'don't know' state, not a 'we are wrong' one --
    and it must not page."""
    import httpx

    def odd_shape(request):
        return httpx.Response(200, json=["not", "a", "dict"])

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(odd_shape))
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["reason"] == "upstream returned an unexpected shape"
    assert body["version_drift"] is False


def test_healthz_cached_drift_result_still_returns_503_without_a_new_upstream_call(client, upstream):
    """C2's cache stores the whole body, including version_drift -- the
    status code must be derived from the cached body on every request, not
    computed once at fetch time and lost when the cached response is served."""
    import httpx

    def drifted(request):
        upstream.calls += 1
        return httpx.Response(200, json={"model_version": "phase3-different"})

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(drifted))
    first = client.get("/healthz")
    assert first.status_code == 503
    assert upstream.calls == 1

    second = client.get("/healthz")
    assert second.status_code == 503
    assert second.json()["version_drift"] is True
    assert upstream.calls == 1


def test_rapid_healthz_hits_make_exactly_one_upstream_call(client, upstream):
    """C2: /healthz is unauthenticated, uncookied, and unthrottled by design
    -- so without a cache it is an amplifier onto the upstream API and its
    database. N hits inside the cache TTL (the clock fixture does not
    auto-advance) must produce exactly one upstream call, not N."""
    for _ in range(50):
        r = client.get("/healthz")
        assert r.status_code == 200
    assert upstream.calls == 1


def test_healthz_refetches_after_the_cache_ttl_expires(client, upstream, clock):
    from app.main import HEALTH_CACHE_TTL_S

    client.get("/healthz")
    assert upstream.calls == 1
    clock.advance(HEALTH_CACHE_TTL_S + 1)
    client.get("/healthz")
    assert upstream.calls == 2


def test_throttle_refusal_logs_the_bound(client, caplog):
    client.get("/")
    with caplog.at_level("INFO", logger="lexicro.demo"):
        for _ in range(20):
            client.post("/api/analyze", json={"text": "Text unic numarul " + str(_)})
        client.post("/api/analyze", json={"text": "Inca unul."})
    assert any(
        record.message.startswith("refused") and "bound=" in record.message
        for record in caplog.records
    )


def test_upstream_bad_request_is_reported_as_bad_input_not_unavailable(client):
    """upstream.py can raise UpstreamError('bad_request') for a real, upstream
    4xx. That is a caller-caused rejection, not an outage, and must not be
    folded into the generic 'unavailable' (502) bucket -- ops would read that
    as our own infrastructure failing when it was never ours to fix."""
    import httpx

    def rejects(request):
        return httpx.Response(400, json={"error": "upstream says no"})

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(rejects))
    client.get("/")
    r = client.post("/api/analyze", json={"text": "Un text care nu e in cache."})
    assert r.status_code == 400
    assert r.json() == {"error": STRINGS["en"]["err_bad_input"]}


def test_malformed_request_body_is_reported_as_bad_input(client):
    """A request body that isn't the {"text": ...} shape we expect is the
    caller's mistake, not an outage -- same err_bad_input copy as an upstream
    bad_request, not the generic err_unavailable it used to get."""
    client.get("/")
    r = client.post(
        "/api/analyze",
        content=b"not json at all",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json() == {"error": STRINGS["en"]["err_bad_input"]}


def test_forged_real_ip_from_a_non_private_peer_is_ignored(app):
    """Reproduces the reviewer's probe. Rotating cookies alone hits ip_burst
    (30 per 10s, keyed on the real peer) at the 31st request. Adding a forged,
    rotating X-Real-IP from a peer that is not loopback/private must land in
    exactly the same place -- the header must never be trusted from a caller
    who isn't actually behind our own reverse proxy. 8.8.8.8 is a real,
    globally-routable address (unlike the 203.0.113.0/24 documentation range,
    which Python's ipaddress module actually classifies as is_private)."""
    with TestClient(app, base_url="https://testserver", client=("8.8.8.8", 12345)) as c:
        admitted = 0
        for i in range(80):
            c.cookies.clear()  # rotate: force a brand-new, validly-signed sid
            c.get("/")
            r = c.post(
                "/api/analyze",
                json={"text": f"Text unic numarul {i}."},
                headers={"X-Real-IP": f"10.{(i // 256) % 256}.{i % 256}.1"},
            )
            if r.status_code == 200:
                admitted += 1
        assert admitted == 30


def test_real_ip_header_is_honoured_from_a_private_peer(app):
    """The counterpart to the test above: when the immediate peer IS
    loopback/private (i.e. actually our own reverse proxy, exactly as in
    production), X-Real-IP must still be honoured -- distinct forwarded IPs
    get distinct per-IP budgets, so many real visitors behind nginx are not
    collapsed into one bucket."""
    with TestClient(app, base_url="https://testserver", client=("10.0.0.1", 12345)) as c:
        admitted = 0
        for i in range(80):
            c.cookies.clear()  # rotate: force a brand-new, validly-signed sid
            c.get("/")
            r = c.post(
                "/api/analyze",
                json={"text": f"Text unic numarul {i}."},
                headers={"X-Real-IP": f"172.16.{(i // 256) % 256}.{i % 256}"},
            )
            if r.status_code == 200:
                admitted += 1
        assert admitted == 80


def test_page_shows_both_hero_pairs(client):
    r = client.get("/")
    assert "Pune sare" in r.text
    assert "Pisica sare" in r.text


def test_page_offers_the_other_language(client):
    from app.strings import STRINGS
    r = client.get("/")
    assert STRINGS["en"]["lang_switch"] in r.text
    assert "?lang=ro" in r.text


def test_page_links_to_the_guide_and_attribution(client):
    r = client.get("/")
    assert "api.lexicro.com/guide" in r.text
    assert "api.lexicro.com/attribution" in r.text


def test_page_declares_the_character_cap(client):
    r = client.get("/")
    assert "500" in r.text


def test_curl_example_uses_the_placeholder_key_if_present(client):
    """Spec section 2 names this as the likeliest accidental key leak, because
    it arrives as a feature request rather than a bug."""
    r = client.get("/")
    if "curl" in r.text:
        assert "lxr_your_key_here" in r.text
    assert SETTINGS.api_key not in r.text


def test_matching_origin_is_allowed(client):
    client.get("/")
    r = client.post(
        "/api/analyze",
        json={"text": "Un text oarecare."},
        headers={"Origin": "https://testserver"},
    )
    assert r.status_code == 200


def test_mismatched_origin_is_rejected(client, upstream):
    """I7: T-3's Origin/Referer half was never implemented -- only the
    cookie check shipped. A cross-site Origin must be rejected even with a
    valid session cookie."""
    client.get("/")
    r = client.post(
        "/api/analyze",
        json={"text": "Un text oarecare."},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert upstream.calls == 0


def test_absent_origin_and_referer_are_allowed(client):
    """TestClient (and most non-browser HTTP clients) send neither header by
    default; the existing suite already exercises this path, but this test
    pins it explicitly so a future tightening of _is_cross_site can't
    silently 403 every caller that omits both headers."""
    client.get("/")
    r = client.post("/api/analyze", json={"text": "Un alt text oarecare."})
    assert r.status_code == 200


def test_different_scheme_same_host_is_rejected(client, upstream):
    """Same host, different scheme -- still cross-site (e.g. a downgrade
    from https to http is exactly the kind of mismatch Origin checking
    exists to catch)."""
    client.get("/")
    r = client.post(
        "/api/analyze",
        json={"text": "Un text oarecare."},
        headers={"Origin": "http://testserver"},
    )
    assert r.status_code == 403
    assert upstream.calls == 0


class _FakeURL:
    def __init__(self, scheme, hostname, port):
        self.scheme = scheme
        self.hostname = hostname
        self.port = port


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    """A minimal stand-in for Starlette's Request: _is_cross_site (and, via
    _is_trusted_peer, _is_cross_site's own forwarded-scheme resolution) only
    ever touches .headers.get(...), .url.{scheme,hostname,port}, and
    .client.host.

    Used instead of TestClient for the default-port and forwarded-scheme
    cases below because TestClient derives request.url straight from
    base_url, so a request made through it can never produce a
    request.url.port that disagrees with the Origin header the way a real
    `Host: host:443` header can, nor an X-Forwarded-Proto that disagrees
    with request.url.scheme independently of the peer address -- the very
    mismatches these tests exist to exercise."""

    def __init__(self, origin, scheme, hostname, port, extra_headers=None, client_host=None):
        self.headers = {} if origin is None else {"origin": origin}
        if extra_headers:
            self.headers.update(extra_headers)
        self.url = _FakeURL(scheme, hostname, port)
        self.client = _FakeClient(client_host) if client_host is not None else None


def test_origin_omitting_default_port_matches_host_carrying_it():
    """I7 port bug: Origin omits the default port (browsers always do this)
    while the request's Host header carries it explicitly (":443"). Both
    describe the same origin and this must be allowed, not 403'd."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin="https://demo.example.com",
        scheme="https",
        hostname="demo.example.com",
        port=443,
    )
    assert _is_cross_site(request) is False


def test_forwarded_proto_from_a_trusted_peer_resolves_the_live_bug():
    """The exact live failure: nginx terminates TLS and proxies over plain
    HTTP, so request.url.scheme is "http" while the browser's Origin is
    "https". From a peer we trust (loopback/private -- i.e. actually our own
    reverse proxy) with X-Forwarded-Proto: https, this must be treated as
    same-site, not rejected."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin="https://testserver",
        scheme="http",
        hostname="testserver",
        port=None,
        extra_headers={"x-forwarded-proto": "https"},
        client_host="10.0.0.5",
    )
    assert _is_cross_site(request) is False


def test_forwarded_proto_does_not_paper_over_a_genuinely_cross_site_origin():
    """The forwarded-scheme fix must not weaken the actual cross-site check:
    a mismatched host is still rejected even once the scheme is corrected."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin="https://evil.example.com",
        scheme="http",
        hostname="testserver",
        port=None,
        extra_headers={"x-forwarded-proto": "https"},
        client_host="10.0.0.5",
    )
    assert _is_cross_site(request) is True


def test_forwarded_proto_from_an_untrusted_peer_is_ignored():
    """A caller reaching this process directly (not via nginx) cannot forge
    X-Forwarded-Proto to talk its way past the check: the raw
    request.url.scheme wins when the immediate peer isn't loopback/private."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin="https://testserver",
        scheme="http",
        hostname="testserver",
        port=None,
        extra_headers={"x-forwarded-proto": "https"},
        client_host="8.8.8.8",
    )
    assert _is_cross_site(request) is True


def test_no_forwarded_proto_header_falls_back_to_the_raw_scheme():
    """When nginx (or any proxy) doesn't send X-Forwarded-Proto at all,
    behaviour is unchanged from before the fix: request.url.scheme is used
    directly, even from a trusted peer."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin="https://testserver",
        scheme="https",
        hostname="testserver",
        port=None,
        client_host="10.0.0.5",
    )
    assert _is_cross_site(request) is False


def test_absent_origin_is_allowed_regardless_of_forwarded_proto():
    """An absent Origin remains allowed unconditionally -- the forwarded-
    scheme resolution only ever runs to compare against a present Origin, so
    it must not change this pre-existing behaviour."""
    from app.main import _is_cross_site

    request = _FakeRequest(
        origin=None,
        scheme="http",
        hostname="testserver",
        port=None,
        extra_headers={"x-forwarded-proto": "https"},
        client_host="10.0.0.5",
    )
    assert _is_cross_site(request) is False


def test_browser_request_behind_a_tls_terminating_proxy_is_not_rejected(app):
    """End-to-end reproduction of the live incident through the real route:
    nginx (peer 10.0.0.1, private/trusted) terminates TLS and proxies to
    this app over plain HTTP, forwarding X-Forwarded-Proto: https; the
    browser sends Origin: https://testserver. The session cookie is seeded
    directly into the jar (rather than obtained via GET /) because a
    Secure-flagged cookie would otherwise be withheld by httpx over a
    plain-http base_url, which would mask the assertion below behind an
    unrelated missing-session 403 -- see the `client` fixture's docstring."""
    from app.session import issue

    with TestClient(app, base_url="http://testserver", client=("10.0.0.1", 12345)) as c:
        c.cookies.set(COOKIE_NAME, issue(SETTINGS.session_secret, "en", 1000.0))
        r = c.post(
            "/api/analyze",
            json={"text": "Un text oarecare."},
            headers={
                "Origin": "https://testserver",
                "X-Forwarded-Proto": "https",
            },
        )
        assert r.status_code != 403


def test_empty_text_is_rejected_as_bad_input(client, upstream):
    client.get("/")
    r = client.post("/api/analyze", json={"text": ""})
    assert r.status_code == 400
    assert r.json() == {"error": STRINGS["en"]["err_bad_input"]}
    assert upstream.calls == 0


def test_whitespace_only_text_is_rejected_as_bad_input(client, upstream):
    client.get("/")
    r = client.post("/api/analyze", json={"text": "   \n\t  "})
    assert r.status_code == 400
    assert r.json() == {"error": STRINGS["en"]["err_bad_input"]}
    assert upstream.calls == 0


def test_semaphore_is_created_by_the_lifespan_context_manager(client):
    """I8: @app.on_event("startup") was replaced with a lifespan context
    manager (the modern, non-deprecated equivalent) -- confirm the semaphore
    it used to create still gets created."""
    assert isinstance(client.app.state.semaphore, asyncio.Semaphore)


def test_create_default_app_configures_logging_for_info(monkeypatch):
    """I6: 'lexicro.demo' had no handler anywhere in its hierarchy and an
    effective level of WARNING, so isEnabledFor(INFO) was False and every
    abuse-detection log line (refused/upstream/hero) was silently dropped --
    the only abuse detection this system has. create_default_app() (the real
    uvicorn entry point, NOT create_app(), which tests call) must leave the
    logger actually enabled for INFO."""
    from app.main import create_default_app

    monkeypatch.setenv("LEXICRO_DEMO_KEY", "lxr_abc")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    logger = logging.getLogger("lexicro.demo")
    try:
        create_default_app()
        assert logger.isEnabledFor(logging.INFO)
        assert logger.handlers, "expected at least one handler, not just a raised level"
    finally:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)


def test_every_data_text_on_the_page_is_a_free_hero_hit(client, upstream):
    """Pins the 'heroes cost nothing' guarantee (FR-027) across heroes.py,
    index.html and main.py together, rather than relying on the three
    agreeing by string coincidence. Renders the real page, extracts every
    data-text attribute the template emits, and posts each one back --
    zero of them may reach upstream."""
    import re

    client.get("/")
    r = client.get("/")
    texts = re.findall(r'data-text="([^"]*)"', r.text)
    assert texts, "expected the template to render at least one data-text attribute"

    import html as html_module
    for text in texts:
        resp = client.post("/api/analyze", json={"text": html_module.unescape(text)})
        assert resp.status_code == 200, (text, resp.text)

    assert upstream.calls == 0


def test_textarea_has_an_associated_label(client):
    """The textarea is the primary interactive element on the page; a
    placeholder alone is not reliably used for accessible-name computation."""
    r = client.get("/")
    assert 'for="text"' in r.text
    assert r.text.index("<label") < r.text.index('<textarea id="text"')
