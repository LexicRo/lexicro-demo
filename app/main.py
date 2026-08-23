"""Routes and wiring.

The order of checks in POST /api/analyze is load-bearing and is spelled out in
spec section 3. In particular the hero cache is consulted BEFORE the throttle,
because FR-027 requires the examples most visitors click to cost no budget.
"""
import logging
import time
from pathlib import Path
from typing import Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, load_settings
from .heroes import Heroes, load, lookup
from .session import COOKIE_NAME, issue, normalise_lang, parse
from .strings import STRINGS, t
from .throttle import Throttle
from .upstream import UpstreamError, analyze, info

BASE_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = BASE_DIR.parent / "fixtures" / "heroes.json"

ERROR_STATUS = {
    "too_long": 400,
    "no_session": 403,
    "throttled": 429,
    "quota": 429,
    "timeout": 504,
    "unavailable": 502,
}

logger = logging.getLogger("lexicro.demo")


def _log(event: str, **fields) -> None:
    # sid is a random token, not a user identifier; the IP is what nginx saw.
    # Never log the text -- it is a stranger's input and we have no reason to
    # keep it.
    logger.info("%s %s", event, " ".join(f"{k}={v}" for k, v in fields.items()))


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The caller's address, not the proxy's.

    Behind nginx, request.client.host is the Docker gateway -- identical for
    every caller -- which would collapse the whole IP backstop into one bucket
    and silently disable it. nginx MUST be setting X-Real-IP; see the spec's
    operations section, which flags this as the line most likely to be
    forgotten and least likely to be noticed.
    """
    if trust_proxy:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # only the rightmost entry was appended by our own proxy
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


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
    app = FastAPI(title="LexicRo demo", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.heroes = heroes
    app.state.clock = clock
    app.state.http = http
    app.state.throttle = Throttle(clock)

    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    def _session_lang(request: Request) -> tuple[str | None, str]:
        s = parse(
            settings.session_secret,
            request.cookies.get(COOKIE_NAME),
            clock(),
            settings.session_max_age_s,
        )
        return (s.sid if s else None), (s.lang if s else "en")

    @app.get("/")
    def index(request: Request, lang: str | None = None):
        existing_sid, existing_lang = _session_lang(request)
        chosen = normalise_lang(lang) if lang else existing_lang
        cookie = issue(settings.session_secret, chosen, clock(), sid=existing_sid)
        response = templates.TemplateResponse(
            request,
            "index.html",
            {
                "lang": chosen,
                "s": STRINGS[chosen],
                "pairs": heroes.pairs,
                "max_chars": settings.max_chars,
                "other_lang": "ro" if chosen == "en" else "en",
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

        try:
            body = await request.json()
            text = body["text"]
            if not isinstance(text, str):
                raise ValueError
        except Exception:
            return JSONResponse(
                {"error": t(lang, "err_unavailable")}, status_code=400
            )

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
                # 6. never forward the upstream body -- T-6
                kind = exc.kind if exc.kind in ("quota", "timeout") else "unavailable"
                return _error(lang, kind)

    @app.get("/healthz")
    async def healthz():
        body = {
            "status": "ok",
            "fixture_model_version": heroes.model_version,
            "live_model_version": None,
        }
        try:
            live = (await info(app.state.http, settings)).get("model_version")
            body["live_model_version"] = live
            if live and live != heroes.model_version:
                body["status"] = "degraded"
                body["reason"] = "hero fixture was generated under a different model_version"
        except UpstreamError:
            body["status"] = "degraded"
            body["reason"] = "upstream unreachable"
        return JSONResponse(body)

    @app.on_event("startup")
    async def _startup():
        import asyncio
        app.state.semaphore = asyncio.Semaphore(settings.upstream_concurrency)

    return app


def _build() -> FastAPI:
    settings = load_settings()
    return create_app(
        settings,
        load(FIXTURE_PATH),
        time.monotonic,
        httpx.AsyncClient(),
    )


class _LazyApp:
    """Defers `_build()` until the app is actually served.

    app.config's own docstring establishes the rule that importing a module
    must not require a populated environment ("Fail by name instead" of
    exploding at import time). `app = _build()` at module scope would break
    that rule here: tests import this module only to reach `create_app`, and
    would otherwise force every test run to configure LEXICRO_DEMO_KEY and
    SESSION_SECRET just to collect. A real deployment missing its .env still
    fails loudly and by name -- just on the first ASGI call instead of at
    import -- via load_settings()'s own RuntimeError.
    """

    def __init__(self) -> None:
        self._instance: FastAPI | None = None

    async def __call__(self, scope, receive, send) -> None:
        if self._instance is None:
            self._instance = _build()
        await self._instance(scope, receive, send)


app = _LazyApp()
