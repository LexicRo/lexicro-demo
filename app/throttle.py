"""The abuse ceiling. Spec section 3.

Every value carries its reasoning, so that anyone tightening one has to argue
with the reason rather than just the number.

try_acquire() both decides AND records in one call. Deliberately not
check-then-record: that split is the non-atomic pattern which is a known open
defect in the API's own rate limiter (OQ-002), and there is no reason to ship
a second instance of it.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Bound:
    name: str
    count: int
    per_seconds: float
    scope: str  # "session" | "ip"


# Order matters: the most specific and most forgiving bound is checked first,
# so the message a real visitor sees is about their own budget, not the room's.
BOUNDS = (
    # A human exploring genuinely never notices 20/hour.
    Bound("session_hour", 20, 3600.0, "session"),
    Bound("session_day", 60, 86400.0, "session"),
    # Catches a script. No room full of people types 30 sentences in 10s.
    Bound("ip_burst", 30, 10.0, "ip"),
    # Deliberately LOOSE. Its job is to stop one runaway host, NOT to be fair:
    # 100 people at a meetup doing 5 each in an hour is 500, under this.
    Bound("ip_hour", 600, 3600.0, "ip"),
)

# The hard bound, and the only real defence against distillation-by-scraping.
# Equals the demo key's daily_limit -- see spec T-5.
GLOBAL_DAILY = 2000
GLOBAL_WINDOW_S = 86400.0


class Throttle:
    def __init__(self, clock: Callable[[], float]):
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._global: deque[float] = deque()

    @staticmethod
    def _prune(window: deque[float], now: float, age: float) -> None:
        while window and window[0] <= now - age:
            window.popleft()

    def try_acquire(self, sid: str, ip: str) -> str | None:
        now = self._clock()
        keys = {"session": sid, "ip": ip}

        windows = []
        for bound in BOUNDS:
            window = self._hits[(bound.name, keys[bound.scope])]
            self._prune(window, now, bound.per_seconds)
            if len(window) >= bound.count:
                return bound.name
            windows.append(window)

        self._prune(self._global, now, GLOBAL_WINDOW_S)
        if len(self._global) >= GLOBAL_DAILY:
            return "global_day"

        # Only now does anything get recorded -- a refusal must not consume
        # budget, or a blocked caller extends their own block by retrying.
        for window in windows:
            window.append(now)
        self._global.append(now)
        return None
