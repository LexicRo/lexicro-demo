import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.heroes import load
from app.main import create_app

SETTINGS = Settings(
    api_base="https://api.test",
    api_key="lxr_super_secret_value",
    session_secret="test-secret",
    trust_proxy=True,
)

HERO_A = "Pune sare în mâncare."
UPSTREAM_PAYLOAD = {
    "model_version": "phase2-baseline-0.1",
    "truncated": False,
    "sentences": [{"tokens": [{"form": "x", "lemma": "x", "upos": "NOUN",
                               "feats": {}, "source": "lexicon"}]}],
}


@pytest.fixture
def fixture_file(tmp_path):
    data = {
        "model_version": "phase2-baseline-0.1",
        "generated_at": "2026-08-23",
        "pairs": [{
            "form": "sare",
            "a": {"text": HERO_A, "analysis": {"sentences": ["cached-a"]}},
            "b": {"text": "Pisica sare pe masă.", "analysis": {"sentences": ["cached-b"]}},
        }],
    }
    p = tmp_path / "heroes.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


class Upstream:
    """Records every call so tests can assert the API was NOT reached."""

    def __init__(self):
        self.calls = 0

    def handler(self, request):
        self.calls += 1
        if request.url.path == "/analyze/info":
            return httpx.Response(200, json={"model_version": "phase2-baseline-0.1"})
        return httpx.Response(200, json=UPSTREAM_PAYLOAD)


@pytest.fixture
def upstream():
    return Upstream()


@pytest.fixture
def clock():
    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t

        def advance(self, s):
            self.t += s

    return Clock()


@pytest.fixture
def app(fixture_file, upstream, clock):
    """The bare FastAPI instance, for tests that need to control the ASGI
    peer address themselves (e.g. the X-Real-IP spoofing tests) rather than
    accepting the `client` fixture's default "testclient" peer."""
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    return create_app(SETTINGS, load(fixture_file), clock, http)


@pytest.fixture
def client(app):
    # base_url is https:// because SETTINGS leaves cookie_secure at its True
    # default (matching production behind TLS): a Secure cookie is withheld
    # by httpx's jar on outgoing requests over plain http, exactly as a real
    # browser would, which would otherwise make every cookie-dependent test
    # here look like a missing-session 403.
    with TestClient(app, base_url="https://testserver") as c:
        yield c
