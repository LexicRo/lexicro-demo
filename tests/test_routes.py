from app.session import COOKIE_NAME
from tests.conftest import HERO_A, SETTINGS


def test_index_renders_and_sets_a_cookie(client):
    r = client.get("/")
    assert r.status_code == 200
    assert COOKIE_NAME in r.cookies


def test_index_never_contains_the_api_key(client):
    """The single most important test in this repo."""
    r = client.get("/")
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
    assert "error" in r.json()


def test_language_switch_preserves_the_session_id(client):
    client.get("/")
    before = client.cookies[COOKIE_NAME]
    client.get("/?lang=ro")
    after = client.cookies[COOKIE_NAME]
    assert before != after  # re-signed
    r = client.get("/")
    assert r.status_code == 200


def test_romanian_page_renders_romanian_copy(client):
    from app.strings import STRINGS
    r = client.get("/?lang=ro")
    assert STRINGS["ro"]["submit"] in r.text


def test_healthz_reports_ok_when_versions_match(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["fixture_model_version"] == "phase2-baseline-0.1"


def test_healthz_reports_degraded_when_the_model_moves(client, upstream, monkeypatch):
    import httpx

    def drifted(request):
        upstream.calls += 1
        return httpx.Response(200, json={"model_version": "phase3-different"})

    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(drifted))
    body = client.get("/healthz").json()
    assert body["status"] == "degraded"


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
