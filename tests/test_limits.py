import threading

import pytest

from xamxam.providers import RateLimiter
from xamxam.whatsapp.limits import MessageDeduplicator, UserRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_queues_requests() -> None:
    clock = FakeClock()
    limiter = RateLimiter(30, clock=clock)
    assert [limiter.reserve() for _ in range(3)] == [0.0, 2.0, 4.0]
    # File de 3 requêtes : la prochaine attend 6 s, 5 de plus en demandent 6 + 4 × 2.
    assert limiter.estimated_wait(5) == pytest.approx(14.0)
    clock.now = 100.0
    assert limiter.reserve() == 0.0
    assert limiter.estimated_wait(0) == 0.0


def test_rate_limiter_is_thread_safe() -> None:
    limiter = RateLimiter(60, clock=lambda: 0.0)
    waits: list[float] = []
    threads = [threading.Thread(target=lambda: waits.append(limiter.reserve())) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(waits) == [float(i) for i in range(50)]


def test_user_rate_limiter_sliding_window() -> None:
    clock = FakeClock()
    limiter = UserRateLimiter(2, window_seconds=3600, clock=clock)
    assert limiter.allow("221770000001", "u1")
    assert limiter.allow("221770000001", "u1")
    assert not limiter.allow("221770000001", "u1")
    assert limiter.allow("221770000002", "u2")
    clock.now = 3600.0
    assert limiter.allow("221770000001", "u1")


def test_unlimited_numbers_are_normalized() -> None:
    limiter = UserRateLimiter(0, unlimited_numbers=frozenset({"221771234567"}))
    assert limiter.allow("221771234567", "u")
    assert not limiter.allow("221770000000", "v")


def test_deduplicator() -> None:
    dedup = MessageDeduplicator(max_size=2)
    assert not dedup.is_duplicate("a")
    assert dedup.is_duplicate("a")
    dedup.is_duplicate("b")
    dedup.is_duplicate("c")  # « a » sort de la mémoire
    assert not dedup.is_duplicate("a")
