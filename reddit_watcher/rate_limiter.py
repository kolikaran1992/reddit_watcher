import asyncio
import time
import random
from reddit_watcher.omniconf import logger


class AsyncRateLimiter:
    """
    Token-bucket based asynchronous rate limiter.
    Supports both bursty and strict (smooth) modes.
    Adds optional random jitter to token refill rate to desynchronize timing.
    """

    def __init__(
        self,
        max_calls: int,
        period: float,
        strict: bool = True,
        jitter_percent: float = 0.1,
    ):
        """
        Args:
            max_calls (int): Maximum number of calls per period.
            period (float): Period in seconds.
            strict (bool): If True, starts empty and refills smoothly.
            jitter_percent (float): Fractional jitter range (e.g., 0.02 = ±2%).
        """
        self.max_calls = max_calls
        self.period = period
        self.allowance = 0 if strict else max_calls
        self.last_check = time.monotonic()
        self._lock = asyncio.Lock()
        self.strict = strict
        self.jitter_percent = jitter_percent

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_check
                self.last_check = now

                # Apply jitter only to token refill rate
                jitter_factor = 1 + random.uniform(
                    -self.jitter_percent, self.jitter_percent
                )
                refill_rate = (self.max_calls / self.period) * jitter_factor

                # Refill tokens with jittered rate
                self.allowance += elapsed * refill_rate

                # cap allowance to avoid bloating it
                if self.allowance > self.max_calls:
                    self.allowance = self.max_calls

                if self.allowance >= 1:
                    logger.info(
                        f"limiter grants one token | allowance={self.allowance:.3f} | jitter={jitter_factor:.3f}"
                    )
                    self.allowance -= 1
                    return

                # Sleep duration stays deterministic
                sleep_for = (1 - self.allowance) * (self.period / self.max_calls)
                logger.info(f"⏳ limiter sleeping for {sleep_for:.3f}s")
                await asyncio.sleep(sleep_for)
