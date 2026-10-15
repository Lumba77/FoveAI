"""
FoveAI CoinEx Integration Module (V2)
=====================================
Secure integration with CoinEx cryptocurrency exchange API V2.
Provides trading, staking, and wallet management functions.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger("coinex_integration")


class CoinExAPIError(Exception):
    """Custom exception for CoinEx API errors."""


try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from resilient_client import get_breaker, parse_retry_after, CircuitBreakerOpenError
except Exception:
    get_breaker = None
    parse_retry_after = lambda x: None
    CircuitBreakerOpenError = Exception


@dataclass
class CoinExConfig:
    api_key: str
    api_secret: str
    base_url: str = "https://api.coinex.com"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class AccountBalance:
    available: dict[str, float]
    frozen: dict[str, float]
    total: dict[str, float]


class CoinExV2Client:
    def __init__(self, config: CoinExConfig):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_signature(
        self, method: str, path: str, body: str, timestamp: str
    ) -> str:
        """Generate HMAC-SHA256 signature for CoinEx V2 API."""
        # Format: METHOD + PATH (including query) + BODY + TIMESTAMP
        prepared_str = f"{method.upper()}{path}{body}{timestamp}"
        logger.info(f"[CoinEx Signature Debug] String: '{prepared_str}'")
        signature = (
            hmac.new(
                self.config.api_secret.encode("latin-1"),
                msg=prepared_str.encode("latin-1"),
                digestmod=hashlib.sha256,
            )
            .hexdigest()
            .lower()
        )
        logger.info(f"[CoinEx Signature Debug] Signature: {signature}")
        return signature

    async def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the CoinEx API."""
        if not self.config.api_key or not self.config.api_secret:
            raise CoinExAPIError("API keys not configured")

        if not path.startswith("/v2") and not path.startswith("/v1"):
            path = f"/v2{path}"

        # Construct path with sorted query params for signature
        full_path = path
        if params:
            query_parts = []
            for key in sorted(params.keys()):
                # Ensure values are converted to string and properly quoted if needed
                query_parts.append(f"{key}={params[key]}")
            full_path = f"{path}?{'&'.join(query_parts)}"

        url = f"{self.config.base_url}{full_path}"

        # Prepare body string (must be "" for GET)
        body_str = json.dumps(body) if body else ""
        timestamp = str(int(time.time() * 1000))

        # Generate signature
        # Format: METHOD + PATH (with query) + BODY + TIMESTAMP
        prepared_str = f"{method.upper()}{full_path}{body_str}{timestamp}"
        signature = (
            hmac.new(
                self.config.api_secret.encode("latin-1"),
                msg=prepared_str.encode("latin-1"),
                digestmod=hashlib.sha256,
            )
            .hexdigest()
            .lower()
        )

        headers = {
            "Content-Type": "application/json",
            "X-COINEX-KEY": self.config.api_key,
            "X-COINEX-SIGN": signature,
            "X-COINEX-TIMESTAMP": timestamp,
        }

        logger.info(f"[CoinEx Request Debug] {method} {full_path} | TS: {timestamp}")

        breaker = get_breaker(self.config.base_url) if get_breaker else None
        if breaker and not breaker.is_available():
            remaining = breaker.remaining_cooldown()
            logger.debug(
                f"[CoinEx Circuit Breaker] Suppressed {method} {full_path} — cooling down ({remaining:.0f}s left)"
            )
            raise CoinExAPIError(f"CoinEx circuit breaker active (cooling down for {remaining:.0f}s)")

        # Retry logic — create a fresh session per attempt to avoid NoneType crashes
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            req_session: aiohttp.ClientSession | None = None
            try:
                # Use the persistent session if available, otherwise create a short-lived one
                if self.session and not self.session.closed:
                    req_session = self.session
                else:
                    req_session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                    )

                # Only pass json body if it exists
                kwargs = {"headers": headers, "timeout": 10}
                if body:
                    kwargs["json"] = body

                async with req_session.request(
                    method.upper(), url, **kwargs
                ) as response:
                    if response.status == 200:
                        res_json = await response.json()
                        code = res_json.get("code", 0)
                        if code != 0:
                            raise CoinExAPIError(
                                f"CoinEx error {code}: {res_json.get('message')}"
                            )
                        if breaker:
                            breaker.record_success()
                        return res_json

                    # Handle server outage / rate-limiting by tripping the circuit breaker immediately
                    if response.status in (429, 500, 502, 503, 504):
                        retry_after = response.headers.get("Retry-After")
                        cooldown = parse_retry_after(retry_after) if parse_retry_after else None
                        if breaker:
                            breaker.trip(cooldown, reason=f"HTTP {response.status}")

                    try:
                        err_data = await response.json()
                        err_msg = f"CoinEx error {err_data.get('code')}: {err_data.get('message')}"
                    except Exception:
                        err_text = await response.text()
                        err_msg = f"CoinEx HTTP {response.status}: {err_text[:200]}"
                    raise CoinExAPIError(err_msg)
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                continue
            finally:
                # Only close sessions we created ourselves (not the persistent one)
                if (
                    req_session
                    and req_session is not self.session
                    and not req_session.closed
                ):
                    await req_session.close()

        if breaker:
            breaker.trip(60.0, reason=f"Network/Timeout error: {last_error}")
        raise CoinExAPIError(
            f"Request failed after {self.config.max_retries} attempts: {last_error}"
        )

    async def get_balance(self, asset: str = "") -> AccountBalance:
        """Fetch spot account balances."""
        path = "/assets/spot/balance"
        resp = await self._make_request("GET", path)

        data = resp.get("data", [])
        available = {}
        frozen = {}
        total = {}

        for entry in data:
            ccy = entry.get("ccy", "")
            if asset and ccy != asset:
                continue

            avail = float(entry.get("available", 0))
            froz = float(entry.get("frozen", 0))
            available[ccy] = avail
            frozen[ccy] = froz
            total[ccy] = avail + froz

        return AccountBalance(available=available, frozen=frozen, total=total)

    async def get_market_price(self, market: str) -> float:
        """Get the current price for a market (e.g. 'BTCUSDT')."""
        path = "/spot/ticker"
        params = {"market": market}
        resp = await self._make_request("GET", path, params=params)
        data = resp.get("data", [])
        if data and isinstance(data, list):
            return float(data[0].get("last", 0))
        return 0.0

    async def place_order(
        self,
        market: str,
        side: str,
        amount: float,
        price: float | None = None,
        order_type: str = "market",
        market_type: str = "SPOT",
    ) -> dict[str, Any]:
        """Place a trade order (CoinEx V2 requires market_type field)."""
        path = "/spot/order"
        body = {
            "market": market,
            "market_type": market_type,
            "side": side.lower(),
            "type": order_type.lower(),
            "amount": str(amount),
        }
        if price:
            body["price"] = str(price)

        return await self._make_request("POST", path, body=body)

    async def withdraw(
        self, coin: str, address: str, amount: float, network: str = "SOL"
    ) -> dict[str, Any]:
        """Withdraw funds to an external address."""
        path = "/assets/withdraw"
        body = {
            "ccy": coin,
            "amount": str(amount),
            "to_address": address,
            "chain": network,
            "withdraw_method": "on_chain",
        }
        return await self._make_request("POST", path, body=body)

    async def get_markets(self) -> list[str]:
        """Fetch list of all spot markets from CoinEx V2 API."""
        try:
            resp = await self._make_request("GET", "/spot/market")
            # CoinEx V2 returns a list of dictionaries with market name, e.g. [{"market": "BTCUSDT", ...}]
            data = resp.get("data", [])
            return [m.get("market") for m in data if m.get("market")]
        except Exception as e:
            logger.error(f"[CoinEx] Failed to get markets: {e}")
            return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "CETUSDT"]

    async def get_market_info(self, market: str) -> dict[str, Any]:
        """Get market trading rules (min amount, precision, etc)."""
        resp = await self._make_request(
            "GET", "/spot/market", params={"market": market}
        )
        data = resp.get("data", [])
        if data:
            return data[0]
        raise CoinExAPIError(f"Market {market} not found")

    async def get_ticker(self, market: str) -> dict[str, Any]:
        """Get ticker info for backward compatibility."""
        try:
            price = await self.get_market_price(market)
            return {"last": price}
        except Exception:
            return {"last": 0.0}

    # V1 interval types (known-working format for /v1/market/kline)
    KLINE_V1_TYPES = [
        "1min",
        "5min",
        "15min",
        "30min",
        "1hour",
        "2hour",
        "4hour",
        "6hour",
        "12hour",
        "1day",
        "3day",
        "1week",
    ]
    # V2 interval formats to try (V2 uses different naming than V1)
    KLINE_V2_FORMATS = ["1hour", "1h", "60", "1min", "5min", "15min", "30min"]

    async def get_kline(
        self,
        market: str,
        interval: str = "1hour",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch kline (candlestick) data from CoinEx API.

        Strategy: Try V1 endpoint first (known-working), then V2 as fallback.
        V1 uses 'type' parameter with values like '1min', '5min', '1hour'.
        V2 uses 'interval' parameter with various formats.

        Args:
            market: Trading pair (e.g. 'BTCUSDT')
            interval: Kline interval (tries V1 then V2 formats automatically)
            limit: Number of candles to return (applied client-side)

        Returns:
            List of kline dicts with keys: timestamp, open, high, low, close, volume
        """
        # --- Strategy 1: V1 endpoint (known-working) ---
        # Map common interval names to V1 type values
        v1_type_map = {
            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "1hour": "1hour",
            "1h": "1hour",
            "60": "1hour",
            "2hour": "2hour",
            "4hour": "4hour",
            "6hour": "6hour",
            "12hour": "12hour",
            "1day": "1day",
            "3day": "3day",
            "1week": "1week",
        }
        v1_type = v1_type_map.get(interval, interval)
        # Build list of V1 types to try: mapped first, then all known V1 types
        v1_types_to_try = [v1_type] + [t for t in self.KLINE_V1_TYPES if t != v1_type]

        for v1_type_val in v1_types_to_try:
            try:
                klines = await self._get_kline_v1(market, v1_type_val, limit)
                if klines:
                    logger.info(
                        f"[CoinEx] get_kline V1 succeeded for {market} with type={v1_type_val}"
                    )
                    return klines
            except CoinExAPIError as e:
                if "4004" in str(e):
                    logger.debug(
                        f"[CoinEx] V1 type={v1_type_val} rejected for {market}, trying next"
                    )
                    continue
                logger.error(
                    f"[CoinEx] V1 get_kline error for {market} type={v1_type_val}: {e}"
                )
                return []

        # --- Strategy 2: V2 endpoint (fallback) ---
        v2_intervals = [interval] + [
            iv for iv in self.KLINE_V2_FORMATS if iv != interval
        ]
        for iv in v2_intervals:
            try:
                klines = await self._get_kline_v2(market, iv, limit)
                if klines:
                    logger.info(
                        f"[CoinEx] get_kline V2 succeeded for {market} with interval={iv}"
                    )
                    return klines
            except CoinExAPIError as e:
                if "4004" in str(e):
                    logger.debug(
                        f"[CoinEx] V2 interval={iv} rejected for {market}, trying next format"
                    )
                    continue
                logger.error(
                    f"[CoinEx] V2 get_kline API error for {market} interval={iv}: {e}"
                )
                return []

        # All methods failed — fall back to ticker-only data
        logger.warning(
            f"[CoinEx] All kline methods failed for {market}. Falling back to ticker-only data."
        )
        return []

    async def _get_kline_v1(
        self,
        market: str,
        kline_type: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch kline data from CoinEx V1 API (/v1/market/kline).

        V1 uses 'type' parameter with values like '1min', '5min', '1hour', etc.
        V1 returns data as a list of arrays: [timestamp, open, close, high, low, volume].
        """
        path = "/v1/market/kline"
        params = {
            "market": market,
            "type": kline_type,
        }
        resp = await self._make_request("GET", path, params=params)
        data = resp.get("data", [])
        if not data:
            logger.debug(f"[CoinEx] No V1 kline data for {market} type={kline_type}")
            return []

        klines: list[dict[str, Any]] = []
        for entry in data:
            if isinstance(entry, list) and len(entry) >= 6:
                # V1 format: [timestamp, open, close, high, low, volume]
                klines.append(
                    {
                        "timestamp": int(entry[0]) if entry[0] else 0,
                        "open": float(entry[1]) if entry[1] else 0.0,
                        "close": float(entry[2]) if entry[2] else 0.0,
                        "high": float(entry[3]) if entry[3] else 0.0,
                        "low": float(entry[4]) if entry[4] else 0.0,
                        "volume": float(entry[5]) if entry[5] else 0.0,
                    }
                )
            elif isinstance(entry, dict):
                klines.append(
                    {
                        "timestamp": int(
                            entry.get("create_time", entry.get("timestamp", 0)) or 0
                        ),
                        "open": float(entry.get("open", 0) or 0),
                        "high": float(entry.get("high", 0) or 0),
                        "low": float(entry.get("low", 0) or 0),
                        "close": float(entry.get("close", 0) or 0),
                        "volume": float(entry.get("volume", 0) or 0),
                    }
                )
        # Apply client-side limit
        if limit > 0 and len(klines) > limit:
            klines = klines[:limit]
        return klines

    async def _get_kline_v2(
        self,
        market: str,
        interval: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch kline data from CoinEx V2 API (/v2/spot/kline).

        V2 uses 'interval' parameter. Format is inconsistent across docs.
        Returns data as list of arrays or dicts depending on API version.
        """
        path = "/v2/spot/kline"
        params = {
            "market": market,
            "interval": interval,
        }
        resp = await self._make_request("GET", path, params=params)
        data = resp.get("data", [])
        if not data:
            logger.debug(f"[CoinEx] No V2 kline data for {market} interval={interval}")
            return []

        klines: list[dict[str, Any]] = []
        for entry in data:
            if isinstance(entry, list) and len(entry) >= 6:
                klines.append(
                    {
                        "timestamp": int(entry[0]) if entry[0] else 0,
                        "open": float(entry[1]) if entry[1] else 0.0,
                        "close": float(entry[2]) if entry[2] else 0.0,
                        "high": float(entry[3]) if entry[3] else 0.0,
                        "low": float(entry[4]) if entry[4] else 0.0,
                        "volume": float(entry[5]) if entry[5] else 0.0,
                    }
                )
            elif isinstance(entry, list) and len(entry) >= 5:
                klines.append(
                    {
                        "timestamp": int(entry[0]) if entry[0] else 0,
                        "open": float(entry[1]) if entry[1] else 0.0,
                        "high": float(entry[2]) if entry[2] else 0.0,
                        "low": float(entry[3]) if entry[3] else 0.0,
                        "close": float(entry[4]) if entry[4] else 0.0,
                        "volume": float(entry[5])
                        if len(entry) > 5 and entry[5]
                        else 0.0,
                    }
                )
            elif isinstance(entry, dict):
                klines.append(
                    {
                        "timestamp": int(
                            entry.get("create_time", entry.get("timestamp", 0)) or 0
                        ),
                        "open": float(entry.get("open", 0) or 0),
                        "high": float(entry.get("high", 0) or 0),
                        "low": float(entry.get("low", 0) or 0),
                        "close": float(entry.get("close", 0) or 0),
                        "volume": float(entry.get("volume", 0) or 0),
                    }
                )
            else:
                logger.debug(
                    f"[CoinEx] Skipping unexpected kline entry type: {type(entry)}"
                )
        # Apply client-side limit
        if limit > 0 and len(klines) > limit:
            klines = klines[:limit]
        return klines
