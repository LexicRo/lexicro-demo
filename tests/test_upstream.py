import httpx
import pytest
from app.config import Settings
from app.upstream import UpstreamError, analyze, info

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
