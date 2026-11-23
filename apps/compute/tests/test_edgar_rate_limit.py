"""The EDGAR rate limiter keeps traffic under SEC's 10 requests/second."""

from __future__ import annotations

import threading

from sextant_compute.data.edgar.client import EDGAR_MAX_PER_SECOND, RateLimiter


class FakeClock:
    """A monotonic clock that only moves when someone sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self._lock = threading.Lock()

    def time(self) -> float:
        with self._lock:
            return self.now

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.now += max(seconds, 0.0)


def max_in_any_second(times: list[float]) -> int:
    times = sorted(times)
    return max(sum(1 for t in times[i:] if t < start + 1.0) for i, start in enumerate(times))


def test_the_configured_rate_is_below_the_sec_limit() -> None:
    assert EDGAR_MAX_PER_SECOND < 10


def test_a_burst_of_requests_never_exceeds_the_limit_in_any_one_second_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_per_second=EDGAR_MAX_PER_SECOND, clock=clock.time, sleep=clock.sleep)

    times = []
    for _ in range(60):
        times.append(limiter.acquire())

    assert max_in_any_second(times) <= EDGAR_MAX_PER_SECOND
    # It throttles rather than stalls: 60 requests take about 60 / rate seconds.
    assert times[-1] - times[0] < 60 / EDGAR_MAX_PER_SECOND + 1


def test_requests_spread_over_time_are_not_delayed() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_per_second=EDGAR_MAX_PER_SECOND, clock=clock.time, sleep=clock.sleep)

    start = clock.time()
    for _ in range(5):
        limiter.acquire()
        clock.sleep(1.0)  # the caller does other work between requests

    assert clock.time() - start == 5.0


def test_concurrent_callers_share_one_limit() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_per_second=EDGAR_MAX_PER_SECOND, clock=clock.time, sleep=clock.sleep)
    times: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(10):
            granted = limiter.acquire()  # the time the request may go out
            with lock:
                times.append(granted)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(times) == 60
    assert max_in_any_second(times) <= EDGAR_MAX_PER_SECOND
