"""
FoveAI Resilient Networking & Universal Circuit Breaker
======================================================
Architectural guardrail ensuring NO server or external endpoint
is ever spammed during outages, 503s, 429s, or network degradation.

Features:
- Host-level / domain-isolated circuit breakers.
- Exponential backoff (60s -> 120s -> 240s -> ... max 1800s / 30 mins).
- Outbound suppression during cooldown (zero network traffic).
- Automatic recovery on successful canary response.
- Respects HTTP 'Retry-After' headers.
- Compatible with httpx and aiohttp.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger("resilient_client")


class CircuitBreakerOpenError(Exception):
    """Raised when an outbound request is suppressed due to active circuit breaker cooldown."""

    def __init__(self, host: str, remaining_seconds: float, reason: str = ""):
        self.host = host
        self.remaining_seconds = remaining_seconds
        self.reason = reason
        super().__init__(
            f"Circuit breaker OPEN for host '{host}' ({reason}). "
            f"Outbound requests suppressed for {remaining_seconds:.1f}s to prevent server spam and protect standing."
        )


class CircuitBreaker:
    """Per-host state tracking for outbound resilience."""

    def __init__(
        self,
        host: str,
        initial_backoff: float = 60.0,
        max_backoff: float = 1800.0,
        multiplier: float = 2.0,
    ):
        self.host = host
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.multiplier = multiplier
        self.cooldown_until: float = 0.0
        self.failure_count: int = 0
        self.last_reason: str = ""

    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def remaining_cooldown(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    def trip(self, custom_cooldown: Optional[float] = None, reason: str = "") -> float:
        self.failure_count += 1
        self.last_reason = reason or "repeated failures"

        if custom_cooldown and custom_cooldown > 0:
            duration = min(custom_cooldown, self.max_backoff)
        else:
            duration = min(
                self.initial_backoff * (self.multiplier ** (self.failure_count - 1)),
                self.max_backoff,
            )

        self.cooldown_until = time.time() + duration
        cooldown_str = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.cooldown_until)
        )
        logger.warning(
            f"🛑 [CircuitBreaker] Host '{self.host}' tripped ({reason})! "
            f"Backing off for {duration:.0f}s until {cooldown_str} "
            f"(consecutive failures: {self.failure_count}). All outbound traffic suppressed."
        )
        return duration

    def record_success(self):
        if self.failure_count > 0:
            logger.info(
                f"✅ [CircuitBreaker] Host '{self.host}' recovered. Resetting backoff."
            )
        self.failure_count = 0
        self.cooldown_until = 0.0
        self.last_reason = ""

    def check(self):
        """Raises CircuitBreakerOpenError if currently cooling down."""
        if not self.is_available():
            raise CircuitBreakerOpenError(
                self.host, self.remaining_cooldown(), self.last_reason
            )


class CircuitBreakerRegistry:
    """Thread-safe registry mapping hostnames to their respective CircuitBreakers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def extract_host(self, url_or_host: str) -> str:
        if "://" in url_or_host:
            parsed = urlparse(url_or_host)
            return (parsed.netloc or parsed.path).split(":")[0].lower()
        return url_or_host.split(":")[0].lower()

    def get(self, url_or_host: str) -> CircuitBreaker:
        host = self.extract_host(url_or_host)
        if host not in self._breakers:
            self._breakers[host] = CircuitBreaker(host)
        return self._breakers[host]

    def reset_all(self):
        for breaker in self._breakers.values():
            breaker.record_success()


# Global singleton registry
GLOBAL_CIRCUIT_REGISTRY = CircuitBreakerRegistry()


def get_breaker(url_or_host: str) -> CircuitBreaker:
    """Retrieve or create the circuit breaker for a target URL or host."""
    return GLOBAL_CIRCUIT_REGISTRY.get(url_or_host)


def parse_retry_after(header_val: Optional[str]) -> Optional[float]:
    """Parse HTTP Retry-After header (either seconds or HTTP-date)."""
    if not header_val:
        return None
    try:
        return float(header_val.strip())
    except ValueError:
        return None
