# reddit_watcher/rate_limiter.py
import asyncio
import time
from reddit_watcher.omniconf import logger


class AsyncRateLimiter:
    """
    Token-bucket based asynchronous rate limiter.
    Supports both bursty and strict (smooth) modes.
    """

    def __init__(self, max_calls: int, period: float, strict: bool = True):
        self.max_calls = max_calls
        self.period = period
        self.allowance = 0 if strict else max_calls  # 👈 strict mode starts empty
        self.last_check = time.monotonic()
        self._lock = asyncio.Lock()
        self.strict = strict

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_check
                self.last_check = now

                # refill tokens
                self.allowance += elapsed * (self.max_calls / self.period)
                if self.allowance > self.max_calls:
                    self.allowance = self.max_calls

                if self.allowance >= 1:
                    logger.info(
                        f"limiter grants one token from {self.allowance:.3f} total tokens"
                    )
                    self.allowance -= 1
                    return

                sleep_for = (1 - self.allowance) * (self.period / self.max_calls)
                logger.info(f"⏳ limiter sleeping for {sleep_for:.3f}s")
                await asyncio.sleep(sleep_for)
