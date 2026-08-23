"""Configuration, read once from the environment.

Deliberately NOT built at import time: importing this module without a
populated environment must not explode. lexicro/app/database.py does build at
import time, and any tool importing it without DATABASE_URL dies with an opaque
ArgumentError -- see 40-roadmap.md. Fail by name instead.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_base: str
    api_key: str
    session_secret: str
    trust_proxy: bool
    max_chars: int = 500
    upstream_timeout_s: float = 10.0
    upstream_concurrency: int = 4
    session_max_age_s: float = 60 * 60 * 24 * 30
    cookie_secure: bool = True


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def load_settings() -> Settings:
    return Settings(
        api_base=os.environ.get(
            "LEXICRO_API_BASE", "https://api.lexicro.com"
        ).rstrip("/"),
        api_key=_require("LEXICRO_DEMO_KEY"),
        session_secret=_require("SESSION_SECRET"),
        trust_proxy=os.environ.get("TRUST_PROXY", "true").lower() == "true",
        cookie_secure=os.environ.get("COOKIE_SECURE", "true").lower() == "true",
    )
