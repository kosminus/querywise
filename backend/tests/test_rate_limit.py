import pytest

from app.core.rate_limit import SlidingWindowRateLimiter


async def test_allows_up_to_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        allowed, _remaining, _retry = await limiter.check("client-a")
        assert allowed is True


async def test_blocks_over_limit():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    await limiter.check("client-a")
    await limiter.check("client-a")
    allowed, remaining, retry_after = await limiter.check("client-a")
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


async def test_keys_are_independent():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    a_allowed, _, _ = await limiter.check("client-a")
    b_allowed, _, _ = await limiter.check("client-b")
    assert a_allowed is True
    assert b_allowed is True


async def test_window_slides(monkeypatch):
    import app.core.rate_limit as rl

    fake_now = {"t": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: fake_now["t"])

    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=10)
    allowed, _, _ = await limiter.check("c")
    assert allowed is True

    # Within the window: blocked.
    allowed, _, _ = await limiter.check("c")
    assert allowed is False

    # Advance past the window: allowed again.
    fake_now["t"] += 11
    allowed, _, _ = await limiter.check("c")
    assert allowed is True


@pytest.mark.parametrize("max_requests", [1, 5, 30])
async def test_remaining_decrements(max_requests):
    limiter = SlidingWindowRateLimiter(max_requests=max_requests, window_seconds=60)
    _allowed, remaining, _retry = await limiter.check("c")
    assert remaining == max_requests - 1
