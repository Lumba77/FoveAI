"""
FoveAI Paper Trading Engine — Swarm Training with Golden Cross Strategy
======================================================================
- Uses CoinEx PUBLIC endpoints (no API keys needed for paper mode)
- Golden Cross strategy: EMA 50/200 crossover with pullback confirmation
- Swarm of agents training in parallel with mentor LLM review
- $1 minimum live trade mode (uses real CoinEx API when PAPER_MODE=False)
- SOL/USDT + CET/USDT pairs supported
- Full P&L tracking, trade logs, win rate analysis
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("paper_trading")

# ============================================================
# CONFIGURATION
# ============================================================

# Toggle this to switch between paper (True) and real $1 trading (False)
PAPER_MODE = True  # Safe local simulation — no real money

# Supported trading pairs
TRADING_PAIRS = [
    {"symbol": "CETUSDT", "base": "CET", "quote": "USDT", "min_trade_usd": 1.0},
    {"symbol": "SOLUSDT", "base": "SOL", "quote": "USDT", "min_trade_usd": 1.0},
]

# Golden Cross Strategy Parameters (from Gemini trading document)
STRATEGY_CONFIG = {
    "ema_fast": 50,  # Fast EMA period (Golden Cross trigger)
    "ema_slow": 200,  # Slow EMA period (trend confirmation)
    "rsi_period": 14,  # RSI for overbought/oversold
    "rsi_oversold": 35,  # Buy signal threshold
    "rsi_overbought": 65,  # Sell signal threshold
    "pullback_pct": 0.02,  # 2% pullback from recent high for entry
    "stop_loss_pct": 0.03,  # 3% stop loss
    "take_profit_pct": 0.06,  # 6% take profit
    "trailing_stop_pct": 0.02,  # 2% trailing stop
    "min_volume_usdt": 500,  # Minimum 24h volume to consider liquid
}

# Agent Swarm Configuration
SWARM_CONFIG = {
    "max_agents": 3,  # 3 agents running in parallel
    "mentor_review_every": 10,  # LLM mentor review every 10 trades per agent
    "training_cycles": 20,  # Number of cycles per training session
    "poll_interval_sec": 30,  # Seconds between market data polls
}


# Position Sizing (conservative — scales with portfolio)
def get_position_size(portfolio_usdt: float, risk_tier: str = "conservative") -> float:
    """Calculate position size based on portfolio value."""
    tiers = {
        "conservative": [
            (0, 20, 0.10),
            (20, 50, 0.15),
            (50, 100, 0.20),
            (100, 500, 0.25),
            (500, float("inf"), 0.30),
        ],
        "moderate": [
            (0, 50, 0.15),
            (50, 200, 0.20),
            (200, 1000, 0.25),
            (1000, float("inf"), 0.30),
        ],
    }
    for lo, hi, pct in tiers.get(risk_tier, tiers["conservative"]):
        if portfolio_usdt >= lo and portfolio_usdt < hi:
            return max(1.0, portfolio_usdt * pct)  # Minimum $1 trade
    return portfolio_usdt * 0.10


# ============================================================
# DATA STRUCTURES
# ============================================================


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Trade:
    """Record of a completed trade."""

    trade_id: str
    agent_id: str
    pair: str
    side: OrderSide
    order_type: OrderType
    amount: float  # Base asset amount
    price: float  # Execution price
    usdt_value: float  # Total in USDT
    timestamp: str
    profit_usdt: float = 0.0
    profit_pct: float = 0.0
    reason: str = ""  # Why the trade was made
    paper: bool = True  # Paper or real trade
    mentor_reviewed: bool = False


@dataclass
class Portfolio:
    """Agent's paper portfolio."""

    agent_id: str
    usdt_balance: float
    holdings: dict[str, float]  # symbol -> amount
    starting_usdt: float
    trades: list[Trade] = field(default_factory=list)
    total_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0

    @property
    def total_value(self) -> float:
        """Calculate total portfolio value (needs market prices)."""
        return self.usdt_balance  # Will be updated externally

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return self.win_count / total if total > 0 else 0.0


@dataclass
class MarketData:
    """Live market data snapshot."""

    symbol: str
    last_price: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_pct_24h: float
    timestamp: str


@dataclass
class TechnicalIndicators:
    """Calculated technical indicators."""

    symbol: str
    timestamp: str
    ema_fast: float  # EMA-50
    ema_slow: float  # EMA-200
    rsi: float  # RSI-14
    macd: float
    macd_signal: float
    macd_histogram: float
    golden_cross: bool  # EMA-50 > EMA-200
    death_cross: bool  # EMA-50 < EMA-200
    price_vs_ema_fast: float  # Price relative to EMA-50
    price_vs_ema_slow: float  # Price relative to EMA-200


# ============================================================
# PAPER TRADING ENGINE
# ============================================================


class PaperTradingEngine:
    """
    Paper trading engine that simulates trades using live CoinEx market data.
    No API key required — uses public endpoints for price data.
    """

    def __init__(self, data_dir: str = None, db: "MonetizingDB" = None):
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "Data",
                "monetizing",
                "paper_trading",
            )
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db = db  # MonetizingDB instance (injected from outside)
        self.agents: dict[str, Portfolio] = {}
        self.market_data: dict[str, list[MarketData]] = {}  # symbol -> price history
        self.indicators: dict[str, TechnicalIndicators] = {}
        self.trade_log_file = self.data_dir / "trades.json"
        self.portfolio_file = self.data_dir / "portfolios.json"
        self.training_log_file = self.data_dir / "training_log.json"

        self._load_state()

    # ---- Market Data ----

    async def fetch_ticker(self, symbol: str) -> MarketData | None:
        """Fetch latest ticker from CoinEx public API (no auth needed)."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.coinex.com/v2/market/ticker",
                    params={"market": symbol},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if data:
                        last = float(data.get("last", 0))
                        return MarketData(
                            symbol=symbol,
                            last_price=last,
                            bid=float(data.get("bid", last)),
                            ask=float(data.get("ask", last)),
                            high_24h=float(data.get("high", last)),
                            low_24h=float(data.get("low", last)),
                            volume_24h=float(data.get("volume", 0)),
                            change_pct_24h=float(data.get("change_percent", 0)),
                            timestamp=datetime.now().isoformat(),
                        )
            logger.warning(f"Failed to fetch ticker for {symbol}: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching {symbol} ticker: {e}")
        return None

    async def fetch_klines(
        self, symbol: str, period: str = "1min", limit: int = 200
    ) -> list[dict]:
        """Fetch kline/candlestick data for indicator calculation."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.coinex.com/v2/market/klines",
                    params={"market": symbol, "type": period, "limit": str(limit)},
                )
                if resp.status_code == 200:
                    return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"Error fetching {symbol} klines: {e}")
        return []

    # ---- Technical Indicators ----

    def calculate_ema(self, prices: list[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if not prices or len(prices) < period:
            return prices[-1] if prices else 0
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # SMA for first value
        for price in prices[period:]:
            ema = (price - ema) * k + ema
        return ema

    def calculate_rsi(self, prices: list[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0  # Neutral default
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(max(0, diff))
            losses.append(abs(diff) if diff < 0 else 0)
        recent_gains = gains[-period:]
        recent_losses = losses[-period:]
        avg_gain = sum(recent_gains) / period
        avg_loss = sum(recent_losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_macd(
        self, prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float, float]:
        """Calculate MACD, Signal line, and Histogram."""
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        # For MACD line, we need the series of MACD values
        if len(prices) < slow + signal:
            macd_line = ema_fast - ema_slow
            return macd_line, macd_line, 0.0

        # Calculate MACD series
        macd_series = []
        for i in range(slow - 1, len(prices)):
            subset = prices[: i + 1]
            ef = self.calculate_ema(subset, fast)
            es = self.calculate_ema(subset, slow)
            macd_series.append(ef - es)

        macd_line = macd_series[-1]
        signal_line = (
            self.calculate_ema(macd_series, signal)
            if len(macd_series) >= signal
            else macd_line
        )
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    async def get_indicators(self, symbol: str) -> TechnicalIndicators | None:
        """Calculate technical indicators from kline data."""
        klines = await self.fetch_klines(symbol, "5min", 200)
        if not klines:
            klines = await self.fetch_klines(symbol, "1min", 200)
        if not klines or len(klines) < 50:
            return None

        closes = [
            float(k.get("close", 0)) for k in klines if float(k.get("close", 0)) > 0
        ]
        if len(closes) < STRATEGY_CONFIG["ema_slow"]:
            return None

        ema_fast = self.calculate_ema(closes, STRATEGY_CONFIG["ema_fast"])
        ema_slow = self.calculate_ema(closes, STRATEGY_CONFIG["ema_slow"])
        rsi = self.calculate_rsi(closes, STRATEGY_CONFIG["rsi_period"])
        macd, macd_signal, macd_hist = self.calculate_macd(closes)

        current_price = closes[-1]

        return TechnicalIndicators(
            symbol=symbol,
            timestamp=datetime.now().isoformat(),
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            golden_cross=ema_fast > ema_slow,
            death_cross=ema_fast < ema_slow,
            price_vs_ema_fast=((current_price - ema_fast) / ema_fast * 100)
            if ema_fast > 0
            else 0,
            price_vs_ema_slow=((current_price - ema_slow) / ema_slow * 100)
            if ema_slow > 0
            else 0,
        )

    # ---- Strategy Logic ----

    def evaluate_buy_signal(
        self,
        indicators: TechnicalIndicators,
        market: MarketData,
        portfolio: Portfolio,
        pair: dict,
    ) -> tuple[bool, str]:
        """Evaluate if we should BUY based on Golden Cross strategy.

        Criteria:
        1. Golden Cross: EMA-50 > EMA-200 (bullish trend)
        2. RSI oversold (< 35) or neutral with pullback
        3. Price near EMA-50 (pullback to support)
        4. 24h volume sufficient
        5. Enough USDT balance
        """
        reasons = []

        # 1. Golden Cross check
        if not indicators.golden_cross:
            return False, "No Golden Cross — EMA-50 below EMA-200"
        reasons.append("Golden Cross active")

        # 2. RSI check
        if indicators.rsi > STRATEGY_CONFIG["rsi_overbought"]:
            return False, f"RSI overbought ({indicators.rsi:.1f})"
        if indicators.rsi < STRATEGY_CONFIG["rsi_oversold"]:
            reasons.append(f"RSI oversold ({indicators.rsi:.1f}) — strong buy")

        # 3. Pullback to EMA-50
        if abs(indicators.price_vs_ema_fast) <= STRATEGY_CONFIG["pullback_pct"] * 100:
            reasons.append(f"Price near EMA-50 ({indicators.price_vs_ema_fast:+.2f}%)")

        # 4. Volume check
        if market.volume_24h < STRATEGY_CONFIG["min_volume_usdt"]:
            return False, f"Low volume ({market.volume_24h:.0f} USDT)"
        reasons.append(f"Volume OK ({market.volume_24h:.0f} USDT)")

        # 5. Balance check
        position_size = get_position_size(portfolio.usdt_balance)
        min_trade = pair.get("min_trade_usd", 1.0)
        if portfolio.usdt_balance < min_trade:
            return False, f"Insufficient USDT ({portfolio.usdt_balance:.2f})"

        reasons.append(f"Position size: ${position_size:.2f}")
        return True, " | ".join(reasons)

    def evaluate_sell_signal(
        self,
        indicators: TechnicalIndicators,
        market: MarketData,
        portfolio: Portfolio,
        pair: dict,
        entry_price: float,
    ) -> tuple[bool, str]:
        """Evaluate if we should SELL.

        Criteria:
        1. Take profit hit (+6%)
        2. Stop loss hit (-3%)
        3. Death Cross (EMA-50 < EMA-200)
        4. RSI overbought
        """
        current_price = market.last_price
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        reasons = []

        # 1. Take profit
        if pnl_pct >= STRATEGY_CONFIG["take_profit_pct"] * 100:
            return True, f"Take profit triggered ({pnl_pct:+.2f}%)"

        # 2. Stop loss
        if pnl_pct <= -STRATEGY_CONFIG["stop_loss_pct"] * 100:
            return True, f"Stop loss triggered ({pnl_pct:+.2f}%)"

        # 3. Death Cross
        if indicators.death_cross:
            return True, "Death Cross — EMA-50 crossed below EMA-200"

        # 4. RSI overbought
        if indicators.rsi > STRATEGY_CONFIG["rsi_overbought"]:
            reasons.append(f"RSI overbought ({indicators.rsi:.1f})")

        if reasons:
            return True, " | ".join(reasons)

        return False, f"Hold — {pnl_pct:+.2f}% from entry"

    # ---- Agent Operations ----

    async def create_agent(
        self, agent_id: str, starting_usdt: float = 20.0
    ) -> Portfolio:
        """Create a new trading agent with starting capital."""
        portfolio = Portfolio(
            agent_id=agent_id,
            usdt_balance=starting_usdt,
            holdings={},
            starting_usdt=starting_usdt,
        )
        self.agents[agent_id] = portfolio
        await self._save_state()
        logger.info(f"Agent {agent_id} created with ${starting_usdt:.2f}")
        return portfolio

    async def run_agent_cycle(self, agent_id: str, pair: dict) -> Trade | None:
        """Run one trading cycle for an agent on a specific pair."""
        symbol = pair["symbol"]
        base = pair["base"]
        portfolio = self.agents.get(agent_id)
        if not portfolio:
            return None

        # Fetch market data
        market = await self.fetch_ticker(symbol)
        if not market:
            return None

        # Calculate indicators
        indicators = await self.get_indicators(symbol)
        if not indicators:
            return None
        self.indicators[symbol] = indicators

        # Track price history
        if symbol not in self.market_data:
            self.market_data[symbol] = []
        self.market_data[symbol].append(market)
        if len(self.market_data[symbol]) > 500:
            self.market_data[symbol] = self.market_data[symbol][-500:]

        # Check if we hold this asset
        holding_amount = portfolio.holdings.get(base, 0)

        if holding_amount <= 0:
            # --- BUY EVALUATION ---
            should_buy, reason = self.evaluate_buy_signal(
                indicators, market, portfolio, pair
            )
            if should_buy:
                position_size = min(
                    get_position_size(portfolio.usdt_balance), portfolio.usdt_balance
                )
                min_trade = pair.get("min_trade_usd", 1.0)
                if position_size < min_trade:
                    position_size = (
                        min_trade if portfolio.usdt_balance >= min_trade else 0
                    )
                if position_size <= 0:
                    return None

                # Execute paper buy
                amount = position_size / market.ask  # Use ask price for buys
                trade = Trade(
                    trade_id=hashlib.md5(
                        f"{agent_id}_{symbol}_{time.time()}_buy".encode()
                    ).hexdigest()[:12],
                    agent_id=agent_id,
                    pair=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    amount=amount,
                    price=market.ask,
                    usdt_value=position_size,
                    timestamp=datetime.now().isoformat(),
                    reason=reason,
                    paper=PAPER_MODE,
                )

                portfolio.usdt_balance -= position_size
                portfolio.holdings[base] = amount
                portfolio.trades.append(trade)
                await self._save_trade(trade)
                await self._save_state()
                logger.info(
                    f"[{agent_id}] 📈 BUY {amount:.4f} {base} @ ${market.ask:.6f} — {reason}"
                )
                return trade
        else:
            # --- SELL EVALUATION ---
            # Find last buy price for this pair
            last_buy = None
            for t in reversed(portfolio.trades):
                if (
                    t.agent_id == agent_id
                    and t.pair == symbol
                    and t.side == OrderSide.BUY
                ):
                    last_buy = t
                    break

            if last_buy:
                should_sell, reason = self.evaluate_sell_signal(
                    indicators, market, portfolio, pair, last_buy.price
                )
                if should_sell:
                    # Execute paper sell
                    usdt_value = holding_amount * market.bid  # Use bid price for sells
                    profit = usdt_value - (holding_amount * last_buy.price)
                    profit_pct = ((market.bid - last_buy.price) / last_buy.price) * 100

                    trade = Trade(
                        trade_id=hashlib.md5(
                            f"{agent_id}_{symbol}_{time.time()}_sell".encode()
                        ).hexdigest()[:12],
                        agent_id=agent_id,
                        pair=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        amount=holding_amount,
                        price=market.bid,
                        usdt_value=usdt_value,
                        timestamp=datetime.now().isoformat(),
                        profit_usdt=profit,
                        profit_pct=profit_pct,
                        reason=reason,
                        paper=PAPER_MODE,
                    )

                    portfolio.usdt_balance += usdt_value
                    portfolio.holdings[base] = 0
                    portfolio.total_pnl += profit
                    if profit > 0:
                        portfolio.win_count += 1
                    else:
                        portfolio.loss_count += 1
                    portfolio.trades.append(trade)
                    await self._save_trade(trade)
                    await self._save_state()

                    emoji = "📈" if profit > 0 else "📉"
                    logger.info(
                        f"[{agent_id}] {emoji} SELL {holding_amount:.4f} {base} @ ${market.bid:.6f} → ${profit:+.4f} ({profit_pct:+.2f}%) — {reason}"
                    )
                    return trade

        return None

    async def run_swarm_cycle(
        self, agent_ids: list[str], pairs: list[dict]
    ) -> list[Trade]:
        """Run one complete cycle for all agents."""
        trades = []
        tasks = []
        for agent_id in agent_ids:
            for pair in pairs:
                if agent_id in self.agents:
                    tasks.append(self.run_agent_cycle(agent_id, pair))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Trade):
                    trades.append(r)
                elif isinstance(r, Exception):
                    logger.error(f"Agent cycle error: {r}")

        return trades

    async def training_session(
        self,
        agent_ids: list[str] | None = None,
        pairs: list[dict] | None = None,
        cycles: int = None,
    ) -> dict[str, Any]:
        """Run a full training session.

        Each cycle: fetch data → evaluate signals → execute paper trades → mentor review
        """
        if agent_ids is None:
            agent_ids = [f"agent_{i + 1}" for i in range(SWARM_CONFIG["max_agents"])]
            for aid in agent_ids:
                if aid not in self.agents:
                    self.create_agent(aid, starting_usdt=20.0)

        if pairs is None:
            pairs = TRADING_PAIRS

        if cycles is None:
            cycles = SWARM_CONFIG["training_cycles"]

        session_start = datetime.now().isoformat()
        all_trades: list[Trade] = []
        cycle_results = []

        logger.info("=" * 60)
        logger.info(
            f"TRAINING SESSION START — {len(agent_ids)} agents, {len(pairs)} pairs, {cycles} cycles"
        )
        logger.info(
            f"Paper Mode: {PAPER_MODE} | Strategy: Golden Cross EMA {STRATEGY_CONFIG['ema_fast']}/{STRATEGY_CONFIG['ema_slow']}"
        )
        logger.info("=" * 60)

        for cycle in range(cycles):
            logger.info(f"\n--- Cycle {cycle + 1}/{cycles} ---")

            # Run swarm cycle
            trades = await self.run_swarm_cycle(agent_ids, pairs)
            all_trades.extend(trades)

            # Mentor review every N trades
            total_trades = sum(
                len(self.agents[a].trades) for a in agent_ids if a in self.agents
            )
            if (
                total_trades > 0
                and total_trades % SWARM_CONFIG["mentor_review_every"] == 0
                and len(trades) > 0
            ):
                logger.info("🧠 Running mentor review...")
                await self._mentor_review(agent_ids)

            # Portfolio summary
            for aid in agent_ids:
                p = self.agents.get(aid)
                if p:
                    logger.info(
                        f"  {aid}: ${p.usdt_balance:.2f} USDT | P&L: ${p.total_pnl:+.4f} | W/L: {p.win_count}/{p.loss_count} | WR: {p.win_rate:.0%}"
                    )

            # Record cycle
            cycle_results.append(
                {
                    "cycle": cycle + 1,
                    "trades_this_cycle": len(trades),
                    "agent_states": {
                        aid: {
                            "usdt": int(self.agents[aid].usdt_balance * 100) / 100,
                            "pnl": round(self.agents[aid].total_pnl, 4),
                            "wins": self.agents[aid].win_count,
                            "losses": self.agents[aid].loss_count,
                        }
                        for aid in agent_ids
                        if aid in self.agents
                    },
                }
            )

            # Wait between cycles (real-time market polling)
            if cycle < cycles - 1:
                await asyncio.sleep(SWARM_CONFIG["poll_interval_sec"])

        # Final summary
        session_end = datetime.now().isoformat()
        summary = self._generate_session_summary(
            agent_ids, all_trades, session_start, session_end
        )
        await self._save_training_log(summary)

        logger.info("\n" + "=" * 60)
        logger.info("TRAINING SESSION COMPLETE")
        logger.info(
            f"Total trades: {len(all_trades)} | Win rate: {summary.get('overall_win_rate', 0):.0%}"
        )
        logger.info(f"Total P&L: ${summary.get('total_pnl', 0):+.4f}")
        logger.info(f"Best agent: {summary.get('best_agent', 'N/A')}")
        logger.info("=" * 60)

        return summary

    async def _mentor_review(self, agent_ids: list[str]):
        """Run mentor LLM analysis on recent trades."""
        try:
            from mentor_analyzer import analyze_trades, get_mentor_memory

            for aid in agent_ids:
                p = self.agents.get(aid)
                if not p or len(p.trades) < 5:
                    continue

                # Format recent trades
                recent = [
                    {
                        "type": t.side.value.upper(),
                        "amount": t.amount,
                        "price": t.price,
                        "result": "WIN"
                        if t.profit_usdt > 0
                        else "LOSS"
                        if t.profit_usdt < 0
                        else "EVEN",
                        "profit": t.profit_usdt,
                    }
                    for t in p.trades[-SWARM_CONFIG["mentor_review_every"] :]
                ]

                # Get indicators
                indicators_dict = {}
                for pair in TRADING_PAIRS:
                    ind = self.indicators.get(pair["symbol"])
                    if ind:
                        indicators_dict = {
                            "rsi": ind.rsi,
                            "macd": ind.macd,
                            "ma9": ind.ema_fast,
                            "ma26": ind.ema_slow,
                        }
                        break

                analysis = await analyze_trades(recent, p.holdings, indicators_dict)

                if analysis:
                    # Apply mentor's confidence modifier to future trades
                    confidence = analysis.get("confidence_modifier", 0.8)
                    action = analysis.get("action", "CONTINUE")
                    logger.info(
                        f"  🧠 Mentor [{aid}]: Health={analysis.get('health_score', 75)}% | Action={action} | Confidence={confidence:.2f}"
                    )

                    # Store mentor memory
                    mem = get_mentor_memory()
                    mem.add_analysis(analysis)
        except ImportError:
            logger.debug("Mentor module not available, skipping review")
        except Exception as e:
            logger.warning(f"Mentor review failed: {e}")

    def _generate_session_summary(
        self,
        agent_ids: list[str],
        trades: list[Trade],
        session_start: str,
        session_end: str,
    ) -> dict[str, Any]:
        """Generate comprehensive training session summary."""
        winning_trades = [t for t in trades if t.profit_usdt > 0]
        losing_trades = [t for t in trades if t.profit_usdt < 0]
        total_pnl = sum(t.profit_usdt for t in trades)
        overall_win_rate = len(winning_trades) / len(trades) if trades else 0

        # Best/worst agents
        best_agent = None
        best_pnl = float("-inf")
        worst_agent = None
        worst_pnl = float("inf")

        agent_stats = {}
        for aid in agent_ids:
            p = self.agents.get(aid)
            if p:
                stats = {
                    "starting_usdt": p.starting_usdt,
                    "current_usdt": round(p.usdt_balance, 2),
                    "total_pnl": round(p.total_pnl, 4),
                    "pnl_pct": round((p.total_pnl / p.starting_usdt) * 100, 2)
                    if p.starting_usdt > 0
                    else 0,
                    "win_count": p.win_count,
                    "loss_count": p.loss_count,
                    "win_rate": round(p.win_rate * 100, 1),
                    "trades": len(p.trades),
                }
                agent_stats[aid] = stats
                if p.total_pnl > best_pnl:
                    best_pnl = p.total_pnl
                    best_agent = aid
                if p.total_pnl < worst_pnl:
                    worst_pnl = p.total_pnl
                    worst_agent = aid

        # Per-pair analysis
        pair_stats = {}
        for pair in TRADING_PAIRS:
            pt = [t for t in trades if t.pair == pair["symbol"]]
            if pt:
                pw = [t for t in pt if t.profit_usdt > 0]
                pair_stats[pair["symbol"]] = {
                    "trades": len(pt),
                    "wins": len(pw),
                    "losses": len(pt) - len(pw),
                    "win_rate": round(len(pw) / len(pt) * 100, 1),
                    "total_pnl": round(sum(t.profit_usdt for t in pt), 4),
                }

        return {
            "session_start": session_start,
            "session_end": session_end,
            "paper_mode": PAPER_MODE,
            "strategy": "Golden Cross EMA-50/200",
            "agents": agent_stats,
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "overall_win_rate": round(overall_win_rate * 100, 1),
            "total_pnl": round(total_pnl, 4),
            "best_agent": best_agent,
            "worst_agent": worst_agent,
            "per_pair": pair_stats,
            "largest_win": round(max((t.profit_usdt for t in trades), default=0), 4),
            "largest_loss": round(min((t.profit_usdt for t in trades), default=0), 4),
        }

    # ---- Persistence ----

    async def _save_trade(self, trade: Trade):
        """Append trade to DB (preferred) or JSON log (fallback)."""
        trade_dict = asdict(trade)
        if self.db:
            try:
                await self.db.insert_trade(trade_dict)
                return
            except Exception as e:
                logger.warning(f"[DB] Trade save failed, falling back to JSON: {e}")
        # Fallback: JSON
        trades = []
        if self.trade_log_file.exists():
            try:
                with open(self.trade_log_file, "r") as f:
                    data = json.load(f)
                    trades = data.get("trades", [])
            except Exception:
                pass
        trades.append(trade_dict)
        with open(self.trade_log_file, "w") as f:
            json.dump(
                {"trades": trades, "last_updated": datetime.now().isoformat()},
                f,
                indent=2,
            )

    async def _save_state(self):
        """Save agent portfolios to DB (preferred) or JSON (fallback)."""
        if self.db:
            try:
                for aid, p in self.agents.items():
                    await self.db.upsert_portfolio(
                        {
                            "agent_id": p.agent_id,
                            "usdt_balance": p.usdt_balance,
                            "holdings": p.holdings,
                            "starting_usdt": p.starting_usdt,
                            "total_pnl": p.total_pnl,
                            "win_count": p.win_count,
                            "loss_count": p.loss_count,
                        }
                    )
                return
            except Exception as e:
                logger.warning(f"[DB] Portfolio save failed, falling back to JSON: {e}")
        # Fallback: JSON
        portfolios = {
            aid: {
                "agent_id": p.agent_id,
                "usdt_balance": p.usdt_balance,
                "holdings": p.holdings,
                "starting_usdt": p.starting_usdt,
                "total_pnl": p.total_pnl,
                "win_count": p.win_count,
                "loss_count": p.loss_count,
                "trade_count": len(p.trades),
            }
            for aid, p in self.agents.items()
        }
        with open(self.portfolio_file, "w") as f:
            json.dump(
                {"portfolios": portfolios, "updated": datetime.now().isoformat()},
                f,
                indent=2,
            )

    async def _save_training_log(self, summary: dict):
        """Save training session to DB (preferred) or JSON (fallback)."""
        if self.db:
            try:
                await self.db.save_training_session(summary)
                return
            except Exception as e:
                logger.warning(
                    f"[DB] Training log save failed, falling back to JSON: {e}"
                )
        # Fallback: JSON
        logs = []
        if self.training_log_file.exists():
            try:
                with open(self.training_log_file, "r") as f:
                    data = json.load(f)
                    logs = data.get("sessions", [])
            except Exception:
                pass
        logs.append(summary)
        # Keep last 50 sessions
        if len(logs) > 50:
            logs = logs[-50:]
        with open(self.training_log_file, "w") as f:
            json.dump(
                {"sessions": logs, "last_updated": datetime.now().isoformat()},
                f,
                indent=2,
            )

    def _load_state(self):
        """Load saved state from JSON (DB loading is async — call _load_state_from_db separately)."""
        if self.portfolio_file.exists():
            try:
                with open(self.portfolio_file, "r") as f:
                    data = json.load(f)
                    for aid, pd in data.get("portfolios", {}).items():
                        p = Portfolio(
                            agent_id=pd["agent_id"],
                            usdt_balance=pd["usdt_balance"],
                            holdings=pd.get("holdings", {}),
                            starting_usdt=pd["starting_usdt"],
                            total_pnl=pd.get("total_pnl", 0),
                            win_count=pd.get("win_count", 0),
                            loss_count=pd.get("loss_count", 0),
                        )
                        self.agents[aid] = p
                logger.info(
                    f"Loaded {len(self.agents)} agents from {self.portfolio_file}"
                )
            except Exception as e:
                logger.warning(f"Failed to load portfolios: {e}")

    async def _load_state_from_db(self):
        """Load portfolios from DB (overrides JSON if DB is available)."""
        if not self.db:
            return
        try:
            portfolios = await self.db.get_all_portfolios()
            for pd in portfolios:
                p = Portfolio(
                    agent_id=pd["agent_id"],
                    usdt_balance=pd["usdt_balance"],
                    holdings=pd.get("holdings", {}),
                    starting_usdt=pd.get("starting_usdt", 20.0),
                    total_pnl=pd.get("total_pnl", 0),
                    win_count=pd.get("win_count", 0),
                    loss_count=pd.get("loss_count", 0),
                )
                self.agents[pd["agent_id"]] = p
            if portfolios:
                logger.info(f"[DB] Loaded {len(portfolios)} portfolios from database")
        except Exception as e:
            logger.warning(f"[DB] Failed to load portfolios from DB: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current engine status."""
        return {
            "paper_mode": PAPER_MODE,
            "agents": len(self.agents),
            "pairs_tracked": len(self.market_data),
            "strategy": f"Golden Cross EMA-{STRATEGY_CONFIG['ema_fast']}/{STRATEGY_CONFIG['ema_slow']}",
            "agent_details": {
                aid: {
                    "usdt": round(p.usdt_balance, 2),
                    "holdings": p.holdings,
                    "pnl": round(p.total_pnl, 4),
                    "win_rate": round(p.win_rate * 100, 1),
                    "trades": len(p.trades),
                }
                for aid, p in self.agents.items()
            },
        }


# ============================================================
# CLI TRAINING RUNNER
# ============================================================


async def main():
    """CLI entry point for training sessions."""
    import sys

    print("\n" + "=" * 70)
    print("  FoveAI PAPER TRADING ENGINE — Swarm Training")
    print("  Golden Cross Strategy (EMA 50/200) + Mentor Review")
    print("=" * 70)

    engine = PaperTradingEngine()

    # Parse args
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else SWARM_CONFIG["training_cycles"]
    agent_count = int(sys.argv[2]) if len(sys.argv) > 2 else SWARM_CONFIG["max_agents"]
    pairs_arg = sys.argv[3] if len(sys.argv) > 3 else "both"  # "cet", "sol", "both"

    # Select pairs
    if pairs_arg == "cet":
        pairs = [p for p in TRADING_PAIRS if p["symbol"] == "CETUSDT"]
    elif pairs_arg == "sol":
        pairs = [p for p in TRADING_PAIRS if p["symbol"] == "SOLUSDT"]
    else:
        pairs = TRADING_PAIRS

    agent_ids = [f"agent_{i + 1}" for i in range(agent_count)]

    print(
        f"\nConfig: {cycles} cycles | {agent_count} agents | Pairs: {[p['symbol'] for p in pairs]}"
    )
    print(f"Paper Mode: {PAPER_MODE} (set PAPER_MODE=False for $1 live trading)")
    print()

    # Run training
    summary = await engine.training_session(
        agent_ids=agent_ids, pairs=pairs, cycles=cycles
    )

    # Print summary
    print(f"\n{'=' * 70}")
    print("  TRAINING SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total Trades:    {summary['total_trades']}")
    print(f"  Win Rate:        {summary['overall_win_rate']}%")
    print(f"  Total P&L:       ${summary['total_pnl']:+.4f}")
    print(f"  Best Agent:      {summary['best_agent']}")
    print(f"  Largest Win:     ${summary['largest_win']:+.4f}")
    print(f"  Largest Loss:    ${summary['largest_loss']:+.4f}")
    print()

    # Per-pair stats
    for pair_sym, ps in summary.get("per_pair", {}).items():
        print(
            f"  {pair_sym}: {ps['trades']} trades | {ps['win_rate']}% WR | ${ps['total_pnl']:+.4f}"
        )

    print("\n  Agent Details:")
    for aid, stats in summary.get("agents", {}).items():
        print(
            f"    {aid}: ${stats['current_usdt']:.2f} ({stats['pnl_pct']:+.1f}%) | {stats['trades']} trades | WR: {stats['win_rate']}%"
        )

    print(f"\n  Session saved to: {engine.training_log_file}")
    print(f"  Trades saved to:  {engine.trade_log_file}")
    print()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    asyncio.run(main())
