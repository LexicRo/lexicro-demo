import httpx
import pytest
from app.config import Settings
from app.upstream import UpstreamError, analyze, conjugate, info

SETTINGS = Settings(
    api_base="https://api.test",
    api_key="lxr_super_secret_value",
    session_secret="s",
    trust_proxy=True,
)


def client_returning(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_key_is_sent_as_a_header_not_in_the_url():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"sentences": []})

    async with client_returning(handler) as c:
        await analyze(c, SETTINGS, "test")

    assert seen["headers"]["X-API-Key"] == "lxr_super_secret_value"
    assert "lxr_super_secret_value" not in seen["url"]


async def test_successful_response_is_returned():
    payload = {"model_version": "v1", "truncated": False, "sentences": [{"tokens": []}]}

    def handler(request):
        return httpx.Response(200, json=payload)

    async with client_returning(handler) as c:
        assert await analyze(c, SETTINGS, "test") == payload


async def test_429_maps_to_quota():
    def handler(request):
        return httpx.Response(429, json={"detail": "quota exceeded for key lxr_abc"})

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as e:
            await analyze(c, SETTINGS, "test")
    assert e.value.kind == "quota"


async def test_500_maps_to_unavailable():
    def handler(request):
        return httpx.Response(500, text="Traceback (most recent call last): ...")

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as e:
            await analyze(c, SETTINGS, "test")
    assert e.value.kind == "unavailable"


async def test_401_maps_to_unavailable_not_bad_request():
    """A bad demo key is our problem, never the visitor's."""
    def handler(request):
        return httpx.Response(401, json={"detail": "invalid key"})

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as e:
            await analyze(c, SETTINGS, "test")
    assert e.value.kind == "unavailable"


async def test_timeout_maps_to_timeout():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as e:
            await analyze(c, SETTINGS, "test")
    assert e.value.kind == "timeout"
    # Verify context attributes are cleared to prevent key leak
    assert e.value.__cause__ is None
    assert e.value.__context__ is None


async def test_error_never_carries_the_upstream_body_or_the_key():
    def handler(request):
        return httpx.Response(500, text="secret internals lxr_super_secret_value")

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as e:
            await analyze(c, SETTINGS, "test")
    rendered = repr(e.value) + str(e.value)
    assert "secret internals" not in rendered
    assert "lxr_super_secret_value" not in rendered
    # Verify context attributes do not carry the key or body
    assert e.value.__cause__ is None
    assert e.value.__context__ is None
    assert "lxr_super_secret_value" not in str(e.value.args)
    assert "secret internals" not in str(e.value.args)


async def test_info_reads_model_version():
    def handler(request):
        assert request.url.path == "/analyze/info"
        return httpx.Response(200, json={"model_version": "phase2-baseline-0.1"})

    async with client_returning(handler) as c:
        assert (await info(c, SETTINGS))["model_version"] == "phase2-baseline-0.1"


async def test_info_sends_the_api_key_header():
    """I3: without this, /healthz lands in the API's anonymous 10/day-per-IP
    bucket instead of the demo key's own budget -- UptimeRobot at 5-minute
    intervals (288/day) means /healthz reports degraded from the first hour
    of every day, and the request is logged upstream with key_hash=NULL."""
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx.Response(200, json={"model_version": "v1"})

    async with client_returning(handler) as c:
        await info(c, SETTINGS)

    assert seen["headers"]["X-API-Key"] == SETTINGS.api_key


async def test_conjugate_percent_encodes_diacritics_and_spaces():
    """`a merge` has a space; real Romanian input has diacritics. Both must
    survive into the path."""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"verb": {}})

    async with client_returning(handler) as c:
        await conjugate(c, SETTINGS, "a minți")

    assert seen["url"] == "https://api.test/conjugate/a%20min%C8%9Bi"


async def test_conjugate_will_not_let_a_verb_escape_the_path():
    """safe="" encodes "/" too, so a verb cannot walk out of the /conjugate/
    prefix into another endpoint."""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"verb": {}})

    async with client_returning(handler) as c:
        await conjugate(c, SETTINGS, "../analyze")

    assert "/conjugate/..%2Fanalyze" in seen["url"]


async def test_conjugate_maps_404_to_not_a_verb():
    """A 404 is the caller typing nonsense, not an outage, and must not be
    reported as one -- the same distinction analyze() draws for 400."""
    def handler(request):
        return httpx.Response(404, json={"detail": "no such verb"})

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as exc:
            await conjugate(c, SETTINGS, "asdfgh")

    assert exc.value.kind == "not_a_verb"


async def test_conjugate_maps_429_to_quota():
    def handler(request):
        return httpx.Response(429, json={"detail": "limit"})

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as exc:
            await conjugate(c, SETTINGS, "merge")

    assert exc.value.kind == "quota"


async def test_conjugate_maps_500_to_unavailable():
    def handler(request):
        return httpx.Response(500, text="boom")

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as exc:
            await conjugate(c, SETTINGS, "merge")

    assert exc.value.kind == "unavailable"


async def test_conjugate_error_never_carries_the_key():
    """T-6. httpx exceptions carry the request object, headers included."""
    def handler(request):
        raise httpx.ConnectError("refused")

    async with client_returning(handler) as c:
        with pytest.raises(UpstreamError) as exc:
            await conjugate(c, SETTINGS, "merge")

    assert SETTINGS.api_key not in repr(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


async def test_conjugate_sends_the_key_as_a_header():
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={"verb": {}})

    async with client_returning(handler) as c:
        await conjugate(c, SETTINGS, "merge")

    assert seen["key"] == SETTINGS.api_key
