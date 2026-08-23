import pytest
from app.throttle import Throttle, GLOBAL_DAILY, GLOBAL_WINDOW_S


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


def test_first_request_is_allowed(clock):
    assert Throttle(clock).try_acquire("s1", "1.1.1.1") is None


def test_session_hour_bound_fires_on_the_twenty_first(clock):
    t = Throttle(clock)
    for _ in range(20):
        assert t.try_acquire("s1", "1.1.1.1") is None
        clock.advance(1)
    assert t.try_acquire("s1", "1.1.1.1") == "session_hour"


def test_session_hour_bound_recovers_after_the_window(clock):
    t = Throttle(clock)
    for _ in range(20):
        t.try_acquire("s1", "1.1.1.1")
        clock.advance(1)
    assert t.try_acquire("s1", "1.1.1.1") == "session_hour"
    clock.advance(3601)
    assert t.try_acquire("s1", "1.1.1.1") is None


def test_sessions_do_not_share_a_budget(clock):
    t = Throttle(clock)
    for _ in range(20):
        t.try_acquire("s1", "1.1.1.1")
        clock.advance(1)
    assert t.try_acquire("s1", "1.1.1.1") == "session_hour"
    assert t.try_acquire("s2", "2.2.2.2") is None


def test_ip_burst_catches_a_script_dropping_cookies(clock):
    """The cookie budget is bypassable by design; this is what actually stops it."""
    t = Throttle(clock)
    for i in range(30):
        assert t.try_acquire(f"fresh-{i}", "9.9.9.9") is None
    assert t.try_acquire("fresh-30", "9.9.9.9") == "ip_burst"


def test_ip_burst_does_not_fire_for_paced_humans(clock):
    t = Throttle(clock)
    for i in range(30):
        assert t.try_acquire(f"visitor-{i}", "9.9.9.9") is None
        clock.advance(2)
    assert t.try_acquire("visitor-30", "9.9.9.9") is None


def test_a_shared_nat_room_is_not_broken(clock):
    """ADR-0021 exists because per-IP fairness breaks a meetup. 100 people
    doing 5 analyses each in an hour is 500 -- under the 600 ceiling."""
    t = Throttle(clock)
    refusals = []
    for round_ in range(5):
        for person in range(100):
            r = t.try_acquire(f"person-{person}", "5.5.5.5")
            if r:
                refusals.append(r)
            clock.advance(7)
    assert refusals == []


def test_ip_hour_ceiling_eventually_fires(clock):
    t = Throttle(clock)
    for i in range(600):
        assert t.try_acquire(f"s-{i}", "7.7.7.7") is None
        clock.advance(1)
    assert t.try_acquire("s-600", "7.7.7.7") == "ip_hour"


def test_global_daily_cap_fires_across_all_sessions_and_ips(clock):
    t = Throttle(clock)
    for i in range(GLOBAL_DAILY):
        assert t.try_acquire(f"s-{i}", f"10.0.{i // 256}.{i % 256}") is None
        clock.advance(10)
    assert t.try_acquire("s-last", "11.11.11.11") == "global_day"


def test_a_refusal_does_not_consume_budget(clock):
    """Otherwise a blocked caller extends their own block by retrying."""
    t = Throttle(clock)
    for _ in range(20):
        t.try_acquire("s1", "1.1.1.1")
        clock.advance(1)
    for _ in range(50):
        assert t.try_acquire("s1", "1.1.1.1") == "session_hour"
    clock.advance(3601)
    assert t.try_acquire("s1", "1.1.1.1") is None


def test_a_refused_request_inserts_no_keys(clock):
    """C1: reading a key must never create one. A defaultdict-backed _hits
    inserts an empty deque merely by being indexed with [], which happens on
    every refusal too -- so a flood of refused requests from unique
    session/IP pairs would retain a key each, forever, and OOM the host.
    A single request that is refused outright (global cap already spent)
    must leave the dict exactly as empty as it started."""
    t = Throttle(clock)
    # Exhaust the global cap first so a *fresh* session/IP pair is refused
    # on its very first try_acquire call -- the case that must add nothing.
    for i in range(GLOBAL_DAILY):
        t.try_acquire(f"warm-{i}", f"10.0.{i // 256}.{i % 256}")
    assert t.try_acquire("brand-new-session", "123.45.67.89") == "global_day"
    assert ("session_hour", "brand-new-session") not in t._hits
    assert ("session_day", "brand-new-session") not in t._hits
    assert ("ip_burst", "123.45.67.89") not in t._hits
    assert ("ip_hour", "123.45.67.89") not in t._hits


def test_swept_dict_shrinks_back_after_windows_expire(clock):
    """C1: even accepted requests must not accumulate keys forever for
    visitors who never return. Every SWEEP_EVERY-th try_acquire call must
    walk the dict and drop any window that has fully aged out."""
    from app.throttle import SWEEP_EVERY

    t = Throttle(clock)
    # One-off visitors: each session/IP pair is used exactly once, so none
    # of these keys is ever touched (and so never pruned) again.
    for i in range(SWEEP_EVERY - 1):
        t.try_acquire(f"once-{i}", f"172.16.{i // 256}.{i % 256}")
    assert len(t._hits) > 0

    # Age every window out, then let the SWEEP_EVERY-th call trigger a sweep.
    clock.advance(GLOBAL_WINDOW_S + 1)
    t.try_acquire("the-1000th-call", "9.9.9.9")

    # Only the keys this very call just inserted survive -- every one of the
    # 999 one-off visitors before it is gone.
    assert set(t._hits) == {
        ("session_hour", "the-1000th-call"),
        ("session_day", "the-1000th-call"),
        ("ip_burst", "9.9.9.9"),
        ("ip_hour", "9.9.9.9"),
    }
