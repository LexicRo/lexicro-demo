"""The visitor cookie: throttle identity plus language preference.

Signed, not encrypted -- nothing in it is secret, it only has to be
unforgeable. ONE cookie rather than two, so that changing language cannot be
used to reset a throttle budget.
"""
import base64
import hmac
import json
import secrets
from dataclasses import dataclass
from hashlib import sha256

COOKIE_NAME = "lxd"
LANGUAGES = ("en", "ro")
# "auto" means follow the OS. Stored server-side in the cookie rather than in
# localStorage so the template can stamp data-theme on <html> in the first
# byte of the response -- a client-side read always flashes the wrong theme.
THEMES = ("auto", "light", "dark")


@dataclass(frozen=True)
class Session:
    sid: str
    lang: str
    theme: str
    issued_at: float


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), sha256).digest())


def normalise_lang(lang: str | None) -> str:
    return lang if lang in LANGUAGES else "en"


def normalise_theme(theme: str | None) -> str:
    return theme if theme in THEMES else "auto"


def issue(
    secret: str,
    lang: str,
    now: float,
    sid: str | None = None,
    theme: str | None = None,
) -> str:
    body = {
        "sid": sid or secrets.token_urlsafe(16),
        "lang": normalise_lang(lang),
        "thm": normalise_theme(theme),
        "iat": now,
    }
    payload = _b64(json.dumps(body, separators=(",", ":")).encode())
    return f"{payload}.{_sign(secret, payload)}"


def parse(secret: str, raw: str | None, now: float, max_age: float) -> Session | None:
    if not raw or raw.count(".") != 1:
        return None
    payload, _, signature = raw.partition(".")
    # constant-time: a timing oracle here leaks the signature byte by byte
    if not hmac.compare_digest(signature, _sign(secret, payload)):
        return None
    try:
        body = json.loads(_unb64(payload))
        sid, issued_at = str(body["sid"]), float(body["iat"])
    except Exception:
        return None
    # 60s of slack for clock skew between issue and parse
    if now - issued_at > max_age or now < issued_at - 60:
        return None
    return Session(
        sid=sid,
        lang=normalise_lang(body.get("lang")),
        theme=normalise_theme(body.get("thm")),
        issued_at=issued_at,
    )
