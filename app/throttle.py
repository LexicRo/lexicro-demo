"""The abuse ceiling. Spec section 3.

Every value carries its reasoning, so that anyone tightening one has to argue
with the reason rather than just the number.

try_acquire() both decides AND records in one call. Deliberately not
check-then-record: that split is the non-atomic pattern which is a known open
defect in the API's own rate limiter (OQ-002), and there is no reason to ship
a second instance of it.
"""
from collections import deque
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

# Age each bound's key by its own window, so the periodic sweep can prune a
# key it has never seen touched at request-time.
_BOUND_AGES = {b.name: b.per_seconds for b in BOUNDS}

# Every Nth try_acquire call pays for a full walk of the dict, so that a key
# for a visitor who never returns (and so never gets pruned on read) does not
# sit there forever. 1000 is cheap relative to the walk it buys.
SWEEP_EVERY = 1000


class Throttle:
    def __init__(self, clock: Callable[[], float]):
        self._clock = clock
        # A plain dict, NOT defaultdict: defaultdict inserts a fresh deque
        # merely by being *read* via [], including for a request that is
        # then refused. Refused requests must leave no trace, or an attacker
        # (or just a busy day) can OOM the host by generating unique
        # session/IP keys that are never evicted -- C1.
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._global: deque[float] = deque()
        self._calls = 0

    @staticmethod
    def _prune(window: deque[float], now: float, age: float) -> None:
        while window and window[0] <= now - age:
            window.popleft()

    def _sweep(self, now: float) -> None:
        """Prune every key's window and drop the ones left empty.

        Without this, a key that is never read again after its last hit --
        the common case, since most visitors do not return -- keeps its
        deque (even once fully aged out) forever, because pruning normally
        only happens as a side effect of a matching try_acquire() call.
        """
        empty = []
        for key, window in self._hits.items():
            age = _BOUND_AGES.get(key[0])
            if age is not None:
                self._prune(window, now, age)
            if not window:
                empty.append(key)
        for key in empty:
            del self._hits[key]

    def try_acquire(self, sid: str, ip: str) -> str | None:
        now = self._clock()
        self._calls += 1
        keys = {"session": sid, "ip": ip}

        for bound in BOUNDS:
            key = (bound.name, keys[bound.scope])
            # .get, never []: reading a key that has never been recorded
            # must not create one. Only an ACCEPTED request, below, does.
            window = self._hits.get(key)
            if window is not None:
                self._prune(window, now, bound.per_seconds)
                if not window:
                    del self._hits[key]
                elif len(window) >= bound.count:
                    return bound.name

        self._prune(self._global, now, GLOBAL_WINDOW_S)
        if len(self._global) >= GLOBAL_DAILY:
            return "global_day"

        # Only now does anything get recorded -- a refusal must not consume
        # budget, or a blocked caller extends their own block by retrying.
        for bound in BOUNDS:
            key = (bound.name, keys[bound.scope])
            window = self._hits.get(key)
            if window is None:
                window = deque()
                self._hits[key] = window
            window.append(now)
        self._global.append(now)

        if self._calls % SWEEP_EVERY == 0:
            self._sweep(now)

        return None
