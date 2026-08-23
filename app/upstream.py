"""The only place the API key is used, and the only place upstream failures
are interpreted.

T-6: nothing from upstream reaches the client verbatim. httpx exceptions carry
the request object -- headers included -- so an unhandled traceback here would
put the key in a response. Every failure is caught and replaced with a bare
`kind`, and UpstreamError deliberately carries no message.
"""
import httpx

from .config import Settings


class UpstreamError(Exception):
    """A failure the caller may classify but must not read."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind

    def __repr__(self) -> str:  # keeps the kind out of nothing, the body out of everything
        return f"UpstreamError({self.kind!r})"


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "X-API-Key": settings.api_key,
        "Content-Type": "application/json",
        "User-Agent": "lexicro-demo",
    }


def _raise(kind: str) -> None:
    """Raise UpstreamError with both __cause__ and __context__ cleared.

    `from None` alone leaves __context__ holding the httpx exception, whose
    request headers carry X-API-Key. We must null both or the key stays reachable.
    """
    err = UpstreamError(kind)
    err.__cause__ = None
    err.__context__ = None
    err.__suppress_context__ = True
    raise err


async def analyze(client: httpx.AsyncClient, settings: Settings, text: str) -> dict:
    error_kind = None
    try:
        response = await client.post(
            f"{settings.api_base}/analyze",
            json={"text": text},
            headers=_headers(settings),
            timeout=settings.upstream_timeout_s,
        )
    except (httpx.TimeoutException,):
        error_kind = "timeout"
    except httpx.HTTPError:
        error_kind = "unavailable"

    if error_kind:
        _raise(error_kind)

    if response.status_code == 429:
        raise UpstreamError("quota")
    if response.status_code == 400:
        raise UpstreamError("bad_request")
    if response.status_code != 200:
        # 401/403 mean OUR key is wrong. That is never the visitor's problem.
        raise UpstreamError("unavailable")

    error_kind = None
    try:
        return response.json()
    except ValueError:
        error_kind = "unavailable"

    if error_kind:
        _raise(error_kind)


async def info(client: httpx.AsyncClient, settings: Settings) -> dict:
    try:
        response = await client.get(
            f"{settings.api_base}/analyze/info",
            timeout=settings.upstream_timeout_s,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        pass

    _raise("unavailable")
