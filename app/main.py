"""Routes and wiring.

The order of checks in POST /api/analyze is load-bearing and is spelled out in
spec section 3. In particular the hero cache is consulted BEFORE the throttle,
because FR-027 requires the examples most visitors click to cost no budget.
"""
import asyncio
import ipaddress
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


class RevalidatingStatic(StaticFiles):
    """StaticFiles that asks the browser to revalidate every time.

    Starlette sends ETag and Last-Modified but no Cache-Control, so browsers
    fall back to HEURISTIC caching and may serve a stale stylesheet without
    ever asking. That is how a deployed CSS fix can be invisible to the very
    people who have seen the page before -- exactly the returning visitors an
    announcement produces.

    `no-cache` does not mean "do not cache"; it means "cache, but revalidate".
    Paired with the ETag Starlette already sends, an unchanged file costs one
    conditional request and a 304 with no body.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
from fastapi.templating import Jinja2Templates

from .config import Settings, load_settings
from .heroes import Heroes, load, lookup
from .session import COOKIE_NAME, issue, normalise_lang, normalise_theme, parse
from .strings import FEATURE_FAMILY, GLOSSES, STRINGS, t
from .throttle import Throttle
from .upstream import UpstreamError, analyze, conjugate, info

BASE_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = BASE_DIR.parent / "fixtures" / "heroes.json"

ERROR_STATUS = {
    "too_long": 400,
    "bad_input": 400,
    "no_session": 403,
    "throttled": 429,
    "quota": 429,
    "timeout": 504,
    "unavailable": 502,
    "not_a_verb": 404,
}

logger = logging.getLogger("lexicro.demo")

# C2: how long a /healthz verdict is served from cache before refreshing.
# UptimeRobot-class monitors poll every few minutes; this bounds /healthz to
# at most one upstream call (and one upstream DB hit) per window, regardless
# of hit rate.
HEALTH_CACHE_TTL_S = 300.0

# A verb is not a paragraph. settings.max_chars is sized for a sentence to
# analyse, and reusing it here would accept a 500-character "verb" and spend an
# upstream call proving it is not one. Deliberately a module constant rather
# than a Settings field: it is not meaningfully operator-tunable, and an env
# var would imply it is.
MAX_VERB_CHARS = 64


def _log(event: str, **fields) -> None:
    # sid is a random token, not a user identifier; the IP is what nginx saw.
    # Never log the text -- it is a stranger's input and we have no reason to
    # keep it.
    logger.info("%s %s", event, " ".join(f"{k}={v}" for k, v in fields.items()))


def _is_trusted_peer(request: Request) -> bool:
    """Only a loopback or private immediate peer may hand us a forwarding header.

    Without this, the guarantee that X-Real-IP is trustworthy lives entirely in
    nginx's config, in a different repo. Any caller who reaches this process
    directly -- bypassing nginx, or in a deployment where it isn't in front --
    could set X-Real-IP to whatever they like and walk straight through the
    per-session and per-IP bounds, leaving only the global daily cap. TestClient
    reports request.client.host as the literal string "testclient", which is
    not a parseable address and so is correctly treated as untrusted here.
    """
    if request.client is None:
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return peer.is_loopback or peer.is_private


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The caller's address, not the proxy's.

    Behind nginx, request.client.host is the Docker gateway -- identical for
    every caller -- which would collapse the whole IP backstop into one bucket
    and silently disable it. nginx MUST be setting X-Real-IP; see the spec's
    operations section, which flags this as the line most likely to be
    forgotten and least likely to be noticed.

    trust_proxy alone is not the gate: it is the operator's declaration that a
    proxy is expected to be present, but a header is only ever honoured when
    the immediate peer is itself loopback or private -- i.e. it could only be
    our own reverse proxy. A caller reaching this process directly, from a
    non-private address, gets its own X-Real-IP/X-Forwarded-For ignored
    outright, so it cannot forge its way around the per-IP backstop.
    """
    if trust_proxy and _is_trusted_peer(request):
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # only the rightmost entry was appended by our own proxy
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin_tuple(scheme: str | None, host: str | None, port: int | None) -> tuple:
    """Scheme/host/port with the scheme's default port made explicit.

    A URL omits its default port and a Host header may carry it, so the raw
    values disagree for the same origin: `https://x` parses to port None
    while `Host: x:443` parses to 443. Comparing raw would 403 a legitimate
    same-site visitor.
    """
    scheme = (scheme or "").lower()
    return (scheme, (host or "").lower(), port or _DEFAULT_PORTS.get(scheme))


def _is_cross_site(request: Request) -> bool:
    """I7: the second half of T-3. Only the cookie check shipped; this is the
    Origin/Referer half.

    A present-but-mismatched Origin is the one shape only a cross-site
    browser request can take (same-site fetches send either a matching
    Origin or none at all), so that is what gets rejected.

    An ABSENT Origin (and Referer) is deliberately treated as allowed, not
    rejected. Browsers omit Origin on plenty of legitimate same-site
    requests, and TestClient -- and most non-browser HTTP clients -- send
    neither header by default; rejecting on absence would 403 the entire
    existing test suite and any tool calling this endpoint directly, for no
    actual security gain (the cookie check above already does the real
    work against those callers).
    """
    origin = request.headers.get("origin")
    if not origin:
        return False
    parsed = urlsplit(origin)

    # Behind a TLS-terminating proxy this app is reached over plain HTTP, so
    # request.url.scheme is "http" while the browser's Origin says "https".
    # Comparing them raw rejects every same-site browser request -- and does so
    # invisibly to curl, which sends no Origin at all. nginx already supplies
    # X-Forwarded-Proto; believe it only from a peer we already trust for
    # X-Real-IP, so a direct caller cannot talk its way past the check.
    scheme = request.url.scheme
    if _is_trusted_peer(request):
        forwarded = request.headers.get("x-forwarded-proto")
        if forwarded:
            scheme = forwarded.split(",")[0].strip().lower()

    return _origin_tuple(parsed.scheme, parsed.hostname, parsed.port) != _origin_tuple(
        scheme, request.url.hostname, request.url.port,
    )


def _error(lang: str, kind: str) -> JSONResponse:
    return JSONResponse(
        {"error": t(lang, f"err_{kind}")},
        status_code=ERROR_STATUS[kind],
    )


def create_app(
    settings: Settings,
    heroes: Heroes,
    clock: Callable[[], float],
    http: httpx.AsyncClient,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # I8: modern replacement for the deprecated @app.on_event("startup").
        # That decorator is slated for removal -- FastAPI dropping it would
        # break every route on a routine `git pull`, with no code change of
        # our own to point at.
        app.state.semaphore = asyncio.Semaphore(settings.upstream_concurrency)
        yield

    app = FastAPI(
        title="LexicRo demo", docs_url=None, redoc_url=None, openapi_url=None,
        lifespan=lifespan,
    )
    # Only app.state.http and app.state.throttle are read anywhere (routes
    # close over settings/heroes/clock directly) -- app.state.http is also
    # reassigned by a test, which is why it stays on state rather than being
    # captured in a closure too.
    app.state.http = http
    app.state.throttle = Throttle(clock)
    # C2: /healthz's cached upstream verdict and the time it was fetched.
    # None means "never fetched yet".
    app.state.health_cache = None

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.mount("/static", RevalidatingStatic(directory=str(BASE_DIR / "static")), name="static")

    def _session_lang(request: Request) -> tuple[str | None, str]:
        s = _session(request)
        return (s.sid if s else None), (s.lang if s else "en")

    def _session(request: Request):
        return parse(
            settings.session_secret,
            request.cookies.get(COOKIE_NAME),
            clock(),
            settings.session_max_age_s,
        )

    @app.api_route("/", methods=["GET", "HEAD"])
    def index(request: Request, lang: str | None = None, theme: str | None = None):
        current = _session(request)
        existing_sid = current.sid if current else None
        chosen = normalise_lang(lang) if lang else (current.lang if current else "en")
        # An explicit ?theme= wins; otherwise keep what the visitor already chose.
        # Both must carry the existing sid, or switching either one would hand the
        # visitor a fresh throttle budget.
        chosen_theme = (
            normalise_theme(theme) if theme else (current.theme if current else "auto")
        )
        cookie = issue(
            settings.session_secret, chosen, clock(),
            sid=existing_sid, theme=chosen_theme,
        )
        response = templates.TemplateResponse(
            request,
            "index.html",
            {
                "lang": chosen,
                "s": STRINGS[chosen],
                "pairs": heroes.pairs,
                "max_chars": settings.max_chars,
                "other_lang": "ro" if chosen == "en" else "en",
                "theme": chosen_theme,
                "glosses": GLOSSES[chosen],
                "families": FEATURE_FAMILY,
            },
        )
        response.set_cookie(
            COOKIE_NAME, cookie,
            max_age=int(settings.session_max_age_s),
            httponly=True, samesite="lax", secure=settings.cookie_secure, path="/",
        )
        return response

    @app.post("/api/analyze")
    async def api_analyze(request: Request):
        sid, lang = _session_lang(request)

        # 1. a valid cookie is required -- T-3, friction against casual scrapers
        if sid is None:
            return _error("en", "no_session")

        # 1b. the other half of T-3 -- see _is_cross_site's docstring for why
        # only a MISMATCHED Origin (not merely an absent one) is rejected.
        if _is_cross_site(request):
            return _error(lang, "no_session")

        try:
            body = await request.json()
            text = body["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except Exception:
            return _error(lang, "bad_input")

        # 2. the cap -- T-2. Server-side is what counts.
        if len(text) > settings.max_chars:
            return _error(lang, "too_long")

        # 3. hero cache BEFORE the throttle -- FR-027
        cached = lookup(heroes, text)
        if cached is not None:
            _log("hero", sid=sid)
            return JSONResponse(cached)

        # 4. the throttle chain
        ip = client_ip(request, settings.trust_proxy)
        refused = app.state.throttle.try_acquire(sid, ip)
        if refused:
            _log("refused", sid=sid, ip=ip, bound=refused)
            return _error(lang, "throttled")

        # 5. bounded concurrency, then upstream
        async with app.state.semaphore:
            try:
                _log("upstream", sid=sid, ip=ip)
                return JSONResponse(await analyze(app.state.http, settings, text))
            except UpstreamError as exc:
                # 6. never forward the upstream body -- T-6. bad_request is a
                # caller-caused rejection, not an outage, and must not be
                # reported as one -- map it to our own bad_input copy rather
                # than folding it into "unavailable".
                if exc.kind == "bad_request":
                    kind = "bad_input"
                elif exc.kind in ("quota", "timeout"):
                    kind = exc.kind
                else:
                    kind = "unavailable"
                return _error(lang, kind)

    @app.post("/api/conjugate")
    async def api_conjugate(request: Request):
        """The subordinate tab's endpoint. The order of checks below is the
        same as api_analyze's and is load-bearing for the same reasons.

        The ONE deliberate difference: there is no hero-cache step. The
        conjugate tab pre-bakes nothing, so it can never serve a form the API
        has stopped serving -- which matters because a table cached before the
        verbecc pin moved would still be showing non-words today.
        """
        sid, lang = _session_lang(request)

        if sid is None:
            return _error("en", "no_session")

        if _is_cross_site(request):
            return _error(lang, "no_session")

        try:
            body = await request.json()
            verb = body["verb"]
            if not isinstance(verb, str) or not verb.strip():
                raise ValueError
        except Exception:
            return _error(lang, "bad_input")

        verb = verb.strip()
        if len(verb) > MAX_VERB_CHARS:
            return _error(lang, "too_long")

        ip = client_ip(request, settings.trust_proxy)
        refused = app.state.throttle.try_acquire(sid, ip)
        if refused:
            _log("refused", sid=sid, ip=ip, bound=refused)
            return _error(lang, "throttled")

        async with app.state.semaphore:
            try:
                _log("upstream", sid=sid, ip=ip)
                return JSONResponse(await conjugate(app.state.http, settings, verb))
            except UpstreamError as exc:
                if exc.kind == "bad_request":
                    kind = "bad_input"
                elif exc.kind in ("quota", "timeout", "not_a_verb"):
                    kind = exc.kind
                else:
                    kind = "unavailable"
                return _error(lang, kind)

    async def _fetch_health() -> dict:
        body = {
            "status": "ok",
            "fixture_model_version": heroes.model_version,
            "live_model_version": None,
            "version_drift": False,
        }
        try:
            # Same semaphore as /api/analyze: without it, /healthz is an
            # unthrottled outbound amplifier -- N concurrent hits would open
            # N upstream connections with a 10s timeout each.
            async with app.state.semaphore:
                live_info = await info(app.state.http, settings)
            live = live_info.get("model_version") if isinstance(live_info, dict) else None
            body["live_model_version"] = live
            if live and live != heroes.model_version:
                body["status"] = "degraded"
                body["reason"] = "hero fixture was generated under a different model_version"
                body["version_drift"] = True
            elif not isinstance(live_info, dict):
                # info() returned something we can't read a version out of.
                # A health endpoint must not raise just because the thing it
                # monitors misbehaved -- report degraded instead.
                body["status"] = "degraded"
                body["reason"] = "upstream returned an unexpected shape"
        except UpstreamError:
            body["status"] = "degraded"
            body["reason"] = "upstream unreachable"
        return body

    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz():
        # C2: /healthz is public, uncookied, and unthrottled by design (a
        # monitor must be able to call it without a session) -- which also
        # makes it an unauthenticated amplifier onto the upstream API and its
        # database if every hit refetches. Cache the verdict for
        # HEALTH_CACHE_TTL_S regardless of how often /healthz itself is hit.
        now = clock()
        cache = app.state.health_cache
        if cache is None or now - cache[0] >= HEALTH_CACHE_TTL_S:
            body = await _fetch_health()
            cache = (now, body)
            app.state.health_cache = cache
        # Only a stale hero fixture (version_drift) pages a monitor with 503:
        # it is persistent and someone must regenerate the fixture. A
        # transient upstream blip or an unreadable response is a "don't
        # know"/"not our fault" state, not an outage of THIS service, and the
        # upstream API already has its own monitoring -- so both stay 200.
        # Keyed on the boolean, not the "reason" prose, so rewording a
        # human-readable reason can never silently flip the status code.
        status_code = 503 if cache[1].get("version_drift") else 200
        return JSONResponse(cache[1], status_code=status_code)

    return app


def create_default_app() -> FastAPI:
    """uvicorn factory entry point: `uvicorn app.main:create_default_app --factory`.

    There is deliberately no module-level `app` here. app.config's own
    docstring establishes the rule that importing a module must not require
    a populated environment ("Fail by name instead" of exploding at import
    time) -- tests import this module only to reach `create_app`, and a
    module-level `app = create_default_app()` would force every test run to
    configure LEXICRO_DEMO_KEY and SESSION_SECRET just to collect.

    The factory idiom also gets failure timing right for a real deployment:
    construction happens at container start, so a broken or missing .env
    refuses to start (matching this project's established refuse-to-serve
    posture, e.g. the API's own migration-gate at startup) rather than
    starting "successfully" and then failing every request.
    """
    # I6: _log() has been silently emitting nothing at all. "lexicro.demo"'s
    # effective level was WARNING (the logging module's own default) and no
    # handler existed anywhere in its hierarchy, so isEnabledFor(INFO) was
    # False and every abuse-detection log line -- "refused", "upstream",
    # "hero" -- was dropped before it was ever formatted. This is the only
    # abuse detection the system has, so it must be configured somewhere
    # real requests actually go through. Deliberately NOT in create_app():
    # tests call that directly and rely on caplog's own level control instead
    # of a global logging config leaking between test runs.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    settings = load_settings()
    return create_app(
        settings,
        load(FIXTURE_PATH),
        time.monotonic,
        httpx.AsyncClient(),
    )
