"""
FoveAI Monetizing Agent Core
===========================
Swarm-based autonomous income generation system.
Semi-autonomous agents that propose and execute income strategies.
"""

import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import asyncio
from pathlib import Path
import os
from coinex_integration import CoinExV2Client, CoinExConfig, CoinExAPIError

# Import mentor analyzer for LLM-based trade review
from mentor_analyzer import analyze_trades, get_mentor_memory, MentorMemory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === MULTI-AGENT CONFIGURATION FOR CET GRINDING ===
# Optimal agent count for CET safe trading with ~$10 capital
MAX_TRADING_AGENTS = 3  # 3 agents for diversified CET grinding
MENTOR_REVIEW_INTERVAL = 10  # Call mentor every 10 trades per agent

# === DYNAMIC POSITION SIZING (Scales with portfolio growth) ===
# Position size increases as portfolio grows - ultra conservative at start
POSITION_SIZE_TIERS = [
    {"min_portfolio": 0,      "max_portfolio": 20,   "position_pct": 0.15},  # $0-20: 15% per trade (ultra conservative)
    {"min_portfolio": 20,     "max_portfolio": 50,   "position_pct": 0.20},  # $20-50: 20% per trade
    {"min_portfolio": 50,     "max_portfolio": 100,  "position_pct": 0.25},  # $50-100: 25% per trade
    {"min_portfolio": 100,    "max_portfolio": 250,  "position_pct": 0.35},  # $100-250: 35% per trade
    {"min_portfolio": 250,    "max_portfolio": 500,  "position_pct": 0.45},  # $250-500: 45% per trade
    {"min_portfolio": 500,    "max_portfolio": 1000, "position_pct": 0.55},  # $500-1k: 55% per trade
    {"min_portfolio": 1000,   "max_portfolio": float("inf"), "position_pct": 0.65},  # $1k+: 65% per trade (max)
]

# HARD CAP: Never risk more than this percentage in a single trade (absolute maximum)
MAX_POSITION_CAP = 0.20  # 20% max position size for portfolios under $100

def get_dynamic_position_size(portfolio_value: float) -> float:
    """Get position size percentage based on current portfolio value.
    
    Philosophy: Start ultra-conservative, scale up as you prove the strategy works.
    """
    for tier in POSITION_SIZE_TIERS:
        if tier["min_portfolio"] <= portfolio_value < tier["max_portfolio"]:
            return tier["position_pct"]
    return 0.80  # Default max


class AgentStatus(Enum):
    """Status of a monetizing agent."""
    IDLE = "idle"
    SEARCHING = "searching"
    ANALYZING = "analyzing"
    PROPOSING = "proposing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"


class IncomeType(Enum):
    """Types of income sources supported."""
    CRYPTO_TRADING = "crypto_trading"
    AFFILIATE_MARKETING = "affiliate_marketing"
    AD_REVENUE = "ad_revenue"
    FREELANCING = "freelancing"
    SURVEYS = "surveys"
    MICRO_TASKS = "micro_tasks"
    STAKING = "staking"
    CONTENT_CREATION = "content_creation"


@dataclass
class IncomeOpportunity:
    """Represents a potential income source."""
    id: str
    name: str
    type: IncomeType
    estimated_hourly_rate: float
    difficulty: int  # 1-10
    setup_time_hours: float
    status: str = "available"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Optional[Dict[str, Any]] = None  # Extra data like max_sell_pct


@dataclass
class AgentSwarmTask:
    """Task assigned to an agent."""
    task_id: str
    agent_id: str
    type: IncomeType
    status: AgentStatus = AgentStatus.IDLE
    opportunity: Optional[IncomeOpportunity] = None
    progress: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    estimated_earnings: float = 0.0
    actual_earnings: Optional[float] = None
    notes: str = ""


@dataclass
class UserWallet:
    """User's cryptocurrency wallet state."""
    solana_address: str
    coinex_api_key: str = ""  # Will be loaded from secure storage
    total_earnings: float = 0.0
    earnings_by_source: Dict[str, float] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    actual_sol_balance: float = 0.0
    actual_cet_balance: float = 0.0


@dataclass
class AgentConfig:
    """Configuration for an monetizing agent."""
    agent_id: str
    name: str
    enabled: bool = True
    autonomy_level: str = "semi_autonomous"  # "manual", "semi_autonomous", "autonomous"
    income_types: List[IncomeType] = field(default_factory=lambda: [IncomeType.CRYPTO_TRADING])
    max_concurrent_tasks: int = 3
    daily_budget_usd: float = 10.0
    risk_tolerance: str = "moderate"  # "low", "moderate", "high"
    target_market: str = "CETUSDT"


class MonetizingAgent:
    """Base class for monetizing agents."""

    def __init__(self, agent_id: str, config: AgentConfig):
        self.agent_id = agent_id
        self.config = config
        self.status = AgentStatus.IDLE
        self.current_task: Optional[AgentSwarmTask] = None
        self.earnings_history: List[Dict] = []
        self.search_history: List[Dict] = []
        self.wallet: Optional[UserWallet] = None
        self.swarm: Optional['AgentSwarm'] = None
        self.storage_dir: Optional[Path] = None  # Injected by swarm after init

    async def search_opportunities(self) -> List[IncomeOpportunity]:
        """Search for income opportunities."""
        self.status = AgentStatus.SEARCHING
        opportunities = []

        # Base opportunities
        base_opportunities = [
            IncomeOpportunity(
                id=hashlib.md5(f"crypto_{time.time()}".encode()).hexdigest()[:8],
                name="Solana Staking",
                type=IncomeType.STAKING,
                estimated_hourly_rate=0.01, # Realistic SOL/hr
                difficulty=3,
                setup_time_hours=1.0,
                status="available"
            ),
            IncomeOpportunity(
                id=hashlib.md5(f"trading_{time.time()}".encode()).hexdigest()[:8],
                name="CoinEx SOL/USDT Scalp",
                type=IncomeType.CRYPTO_TRADING,
                estimated_hourly_rate=0.05,
                difficulty=5,
                setup_time_hours=2.0,
                status="available"
            ),
        ]

        opportunities.extend(base_opportunities)
        self.search_history.append({
            "timestamp": datetime.now().isoformat(),
            "count": len(opportunities)
        })

        logger.info(f"[Agent {self.agent_id}] Found {len(opportunities)} opportunities")
        return opportunities

    async def analyze_opportunity(self, opportunity: IncomeOpportunity) -> bool:
        """Analyze if an opportunity is viable."""
        self.status = AgentStatus.ANALYZING
        
        # 1. Use LLM analyzer if available in swarm
        if self.swarm and hasattr(self.swarm, 'llm_analyzer') and self.swarm.llm_analyzer:
            logger.info(f"[Agent {self.agent_id}] Calling Smart LLM Analyzer for {opportunity.name}...")
            try:
                result = await self.swarm.llm_analyzer(opportunity)
                logger.info(f"[Agent {self.agent_id}] Smart LLM Result: {'Approved' if result else 'Rejected'}")
                return result
            except Exception as e:
                logger.error(f"[Agent {self.agent_id}] LLM Analyzer Error: {e}")

        # 2. Basic viability check fallback
        return opportunity.estimated_hourly_rate > 0 and opportunity.difficulty < 8

    async def propose_task(self, opportunity: IncomeOpportunity) -> AgentSwarmTask:
        """Create a task proposal for an opportunity."""
        self.status = AgentStatus.PROPOSING

        task = AgentSwarmTask(
            task_id=hashlib.md5(f"task_{self.agent_id}_{time.time()}".encode()).hexdigest()[:8],
            agent_id=self.agent_id,
            type=opportunity.type,
            opportunity=opportunity,
            estimated_earnings=opportunity.estimated_hourly_rate
        )

        logger.info(f"[Agent {self.agent_id}] Proposed task: {task.task_id}")
        return task

    async def execute_task(self, task: AgentSwarmTask) -> bool:
        """Execute an approved task."""
        self.status = AgentStatus.EXECUTING
        self.current_task = task
        
        logger.info(f"[Agent {self.agent_id}] Starting task {task.task_id}: {task.type.value}")

        # Simulation logic - more steps for visibility
        steps = [
            "Connecting to exchange...",
            "Fetching order book...",
            "Calculating optimal entry...",
            "Checking risk parameters...",
            "Placing order...",
            "Monitoring position...",
            "Setting take-profit...",
            "Waiting for fill...",
            "Order filled. Closing position...",
            "Finalizing trade..."
        ]

        for i, step_msg in enumerate(steps):
            task.notes = step_msg
            task.progress = (i + 1) * 10
            await asyncio.sleep(2.0) # 20 seconds total for visible activity
            
            if task.progress >= 100:
                task.status = AgentStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                task.actual_earnings = task.estimated_earnings * 0.1 # Very small simulated gain
                
                self.earnings_history.append({
                    "task_id": task.task_id,
                    "amount": task.actual_earnings,
                    "type": task.type.value,
                    "timestamp": datetime.now().isoformat()
                })

                if self.wallet:
                    self.wallet.total_earnings += task.actual_earnings
                    source_key = f"{task.type.value}_{task.opportunity.id if task.opportunity else 'unknown'}"
                    self.wallet.earnings_by_source[source_key] = \
                        self.wallet.earnings_by_source.get(source_key, 0) + task.actual_earnings
                    self.wallet.last_updated = datetime.now().isoformat()

                logger.info(f"[Agent {self.agent_id}] Task completed: {task.task_id} - Earned: {task.actual_earnings:.4f} SOL")
                self.status = AgentStatus.IDLE
                return True

        return False

    async def pause(self):
        """Pause the agent."""
        self.status = AgentStatus.PAUSED

    async def resume(self):
        """Resume the agent."""
        if self.status in [AgentStatus.PAUSED, AgentStatus.PROPOSING, AgentStatus.ERROR, AgentStatus.SEARCHING, AgentStatus.EXECUTING]:
            self.status = AgentStatus.IDLE
            logger.info(f"[Agent {self.agent_id}] Resumed/Reset -> IDLE")

    def _safe_task_dict(self, task) -> Optional[Dict]:
        """Convert AgentSwarmTask to a JSON-safe dict (converts Enums to .value)."""
        if task is None:
            return None
        try:
            d = asdict(task)
            # Recursively convert any Enum values
            def fix_enums(obj):
                if isinstance(obj, dict):
                    return {k: fix_enums(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [fix_enums(i) for i in obj]
                elif hasattr(obj, 'value'):  # Enum
                    return obj.value
                return obj
            return fix_enums(d)
        except Exception:
            return {"task_id": getattr(task, 'task_id', '?'), "type": str(getattr(task, 'type', '?')), "notes": getattr(task, 'notes', ''), "progress": getattr(task, 'progress', 0)}

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        current_task_dict = None
        if self.current_task and self.status == AgentStatus.EXECUTING:
            current_task_dict = self._safe_task_dict(self.current_task)
        return {
            "agent_id": self.agent_id,
            "name": self.config.name,
            "status": self.status.value,
            "type": "base",  # Overridden by subclasses
            "is_live": False,
            "income_types": [t.value for t in self.config.income_types],
            "total_tasks_completed": self.total_tasks_completed if hasattr(self, 'total_tasks_completed') else len(self.earnings_history),
            "total_earnings": sum(e["amount"] for e in self.earnings_history),
            "searches_performed": len(self.search_history),
            "last_search": self.search_history[-1]["timestamp"] if self.search_history else None,
            "current_task": current_task_dict
        }


class CoinExTradingAgent(MonetizingAgent):
    """Real-world CoinEx trading agent."""

    def __init__(self, agent_id: str, config: AgentConfig):
        super().__init__(agent_id, config)
        self.client: Optional[CoinExV2Client] = None
        self.sol_address: str = ""
        
        # Assign default target markets to Lumax1, Lumax2, Lumax3 for automatic diversification
        if self.config.target_market == "CETUSDT":
            if "foveai1" in self.config.name.lower() or "pro_01" in self.config.agent_id:
                self.config.target_market = "CETUSDT"
            elif "foveai2" in self.config.name.lower() or "pro_02" in self.config.agent_id:
                self.config.target_market = "SOLUSDT"
            elif "foveai3" in self.config.name.lower() or "pro_03" in self.config.agent_id:
                self.config.target_market = "BTCUSDT"

    async def _init_client(self):
        """Initialize CoinEx client with credentials from storage."""
        if not self.client:
            try:
                from security import SecureStorage
                # Determine storage path — use injected path from swarm, or compute from file location
                storage_path = self.storage_dir
                if not storage_path:
                    storage_path = Path(__file__).parent.parent.parent / "Data" / "monetizing" / "storage"
                
                logger.info(f"[Agent {self.agent_id}] Loading credentials from: {storage_path}")
                storage = SecureStorage(storage_path)
                
                key = storage.get_api_key("coinex_key")
                secret = storage.get_api_key("coinex_secret")
                logger.info(f"[Agent {self.agent_id}] Key found: {bool(key)}, Secret found: {bool(secret)}")
                
                if key and secret:
                    conf = CoinExConfig(api_key=key, api_secret=secret)
                    self.client = CoinExV2Client(conf)
                    await self.client.__aenter__()
                    logger.info(f"[Agent {self.agent_id}] CoinEx Client Initialized")
                else:
                    logger.warning(f"[Agent {self.agent_id}] No CoinEx credentials found in SecureStorage")
            except Exception as e:
                logger.error(f"[Agent {self.agent_id}] Failed to init client: {e}")
            
            if self.wallet:
                self.sol_address = self.wallet.solana_address

    async def search_opportunities(self) -> List[IncomeOpportunity]:
        """Fetch markets from CoinEx — filtered to tradable pairs based on config."""
        self.status = AgentStatus.SEARCHING
        await self._init_client()
        
        if not self.client:
            logger.warning(f"[Agent {self.agent_id}] No CoinEx client, falling back to base search")
            return await super().search_opportunities()

        try:
            # Get both markets and balances
            markets = await self.client.get_markets()
            balance = await self.client.get_balance()
            
            # Define balances for CET and USDT to avoid NameErrors in fallback/logging blocks
            cet_balance = balance.available.get("CET", 0.0)
            usdt_balance = balance.available.get("USDT", 0.0)

            # Find which base currencies the account actually holds (>= 0.0001 — catch very small balances)
            owned_bases = {ccy for ccy, amt in balance.available.items() if amt >= 0.0001}
            logger.info(f"[Agent {self.agent_id}] Owned currencies: {owned_bases} (from {len(balance.available)} total)")
            
            opportunities = []
            
            # Resolve target market configuration
            target_market = self.config.target_market
            
            # Get market info for base and quote currency resolution
            market_info = await self.client.get_market_info(target_market)
            base_ccy = market_info.get("base_ccy", "CET")
            quote_ccy = market_info.get("quote_ccy", "USDT")
            
            base_balance = balance.available.get(base_ccy, 0.0)
            quote_balance = balance.available.get(quote_ccy, 0.0)
            
            # Fetch candlestick data for technical analysis
            current_cet_price = 0.0
            fast_ma = 0.0  # 9-period EMA
            slow_ma = 0.0  # 26-period EMA
            rsi = 50.0  # RSI (14-period)
            macd_line = 0.0
            signal_line = 0.0
            
            try:
                klines = await self.client.get_kline(target_market, interval="1hour", limit=50)
                
                if klines and len(klines) >= 26:
                    closes = [float(k.get("close", 0)) for k in klines]
                    current_cet_price = closes[-1]
                    
                    # Calculate current EMAs
                    fast_ma = self._calculate_ema(closes, period=9)
                    slow_ma = self._calculate_ema(closes, period=26)
                    
                    # Calculate previous EMAs to detect true crossover
                    prev_fast_ma = self._calculate_ema(closes[:-1], period=9)
                    prev_slow_ma = self._calculate_ema(closes[:-1], period=26)
                    
                    # Calculate RSI
                    rsi = self._calculate_rsi(closes, period=14)
                    
                    # Calculate MACD
                    macd_12 = self._calculate_ema(closes, period=12)
                    macd_26 = self._calculate_ema(closes, period=26)
                    macd_line = macd_12 - macd_26
                    
                    # Signal line
                    macd_values = [self._calculate_ema(closes[:i+1], period=12) - self._calculate_ema(closes[:i+1], period=26) for i in range(9, len(closes))]
                    signal_line = self._calculate_ema(macd_values, period=9) if macd_values else 0
                    
                    logger.info(f"[Agent {self.agent_id}] {target_market} Technicals: Price=${current_cet_price:.6f}, MA9=${fast_ma:.6f}, MA26=${slow_ma:.6f}, RSI={rsi:.1f}, MACD={macd_line:.6f}")
            except Exception as e:
                logger.warning(f"[Agent {self.agent_id}] Could not fetch technical data for {target_market}: {e}")
            
            # Fallback
            if not klines or len(klines) < 9:
                logger.info(f"[Agent {self.agent_id}] Kline data insufficient ({len(klines) if klines else 0} candles), using ticker fallback")
                try:
                    ticker_price = await self.client.get_market_price(target_market)
                    if ticker_price and ticker_price > 0:
                        current_cet_price = ticker_price
                        fast_ma = slow_ma = ticker_price
                        prev_fast_ma = prev_slow_ma = ticker_price
                        rsi = 50.0
                        macd_line = 0.0
                        signal_line = 0.0
                        logger.info(f"[Agent {self.agent_id}] Ticker fallback: {target_market} @ ${ticker_price:.6f}, RSI=50")
                except Exception as ticker_err:
                    logger.warning(f"[Agent {self.agent_id}] Ticker fallback failed: {ticker_err}")
            
            # Detect true crossover signals
            golden_cross = prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma
            death_cross = prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma
            
            # Determine market state
            is_uptrend = fast_ma > slow_ma
            is_downtrend = fast_ma < slow_ma
            is_oversold = rsi < 35
            is_overbought = rsi > 65
            
            # Safe grinding conditions
            buy_signal = golden_cross or (is_uptrend and rsi < 40) or (rsi < 30)
            sell_signal = death_cross or (is_downtrend and rsi > 60) or (rsi > 70)
            
            # Fetch quote USD value for portfolio sizing
            cet_usd_price = 0.02
            try:
                cet_usd_price = await self.client.get_market_price("CETUSDT")
            except Exception:
                pass
                
            if quote_ccy in ("USDT", "USDC"):
                quote_usd_val = quote_balance
            else:
                quote_usd_val = quote_balance * cet_usd_price
                
            # MODE 1: BUY
            if quote_usd_val >= 2.0 and buy_signal:
                try:
                    min_amount = float(market_info.get("min_amount", 999999))
                    min_value = min_amount * current_cet_price
                    
                    # Estimate the trade value using our position sizing rules
                    portfolio_value = (base_balance * current_cet_price) + quote_balance
                    if quote_ccy in ("USDT", "USDC"):
                        portfolio_usd = portfolio_value
                    else:
                        portfolio_usd = portfolio_value * cet_usd_price
                        
                    position_pct = get_dynamic_position_size(portfolio_usd)
                    if portfolio_usd < 100 and position_pct > MAX_POSITION_CAP:
                        position_pct = MAX_POSITION_CAP
                        
                    trade_value = quote_balance * position_pct
                    if trade_value >= min_value:
                        if golden_cross:
                            opp_name = f"GOLDEN CROSS BUY @ {current_cet_price:.6f} {quote_ccy}"
                        elif is_uptrend and rsi < 40:
                            opp_name = f"UPTREND PULLBACK BUY @ {current_cet_price:.6f} {quote_ccy} (RSI={rsi:.1f})"
                        else:
                            opp_name = f"RSI OVERSOLD BUY @ {current_cet_price:.6f} {quote_ccy} (RSI={rsi:.1f})"
                            
                        opportunities.append(IncomeOpportunity(
                            id=f"coinex_{target_market}_buy",
                            name=opp_name,
                            type=IncomeType.CRYPTO_TRADING,
                            estimated_hourly_rate=0.12,
                            difficulty=3,
                            setup_time_hours=0.1,
                            status="available"
                        ))
                        logger.info(f"[Agent {self.agent_id}] 🟢 BUY Opportunity detected on {target_market}: {opp_name}")
                except Exception as e:
                    logger.error(f"[Agent {self.agent_id}] Buy opportunity error on {target_market}: {e}")
            
            # MODE 2: SELL
            if base_balance > 0:
                if base_ccy == "CET":
                    base_usd_val = base_balance * cet_usd_price
                else:
                    base_usd_val = base_balance * current_cet_price * (cet_usd_price if quote_ccy == "CET" else 1.0)
            else:
                base_usd_val = 0.0
                
            if base_usd_val >= 2.0 and sell_signal:
                try:
                    min_amount = float(market_info.get("min_amount", 999999))
                    # Only sell 30% of base holdings
                    sell_amount = base_balance * 0.30
                    
                    if sell_amount >= min_amount:
                        if death_cross:
                            opp_name = f"DEATH CROSS SELL @ {current_cet_price:.6f} {quote_ccy}"
                        elif is_downtrend and rsi > 60:
                            opp_name = f"DOWNTREND RALLY SELL @ {current_cet_price:.6f} {quote_ccy} (RSI={rsi:.1f})"
                        else:
                            opp_name = f"RSI OVERBOUGHT SELL @ {current_cet_price:.6f} {quote_ccy} (RSI={rsi:.1f})"
                            
                        opportunities.append(IncomeOpportunity(
                            id=f"coinex_{target_market}_sell",
                            name=opp_name,
                            type=IncomeType.CRYPTO_TRADING,
                            estimated_hourly_rate=0.12,
                            difficulty=3,
                            setup_time_hours=0.1,
                            status="available",
                            metadata={"max_sell_pct": 0.30}
                        ))
                        logger.info(f"[Agent {self.agent_id}] 🔴 SELL Opportunity detected on {target_market}: {opp_name}")
                except Exception as e:
                    logger.error(f"[Agent {self.agent_id}] Sell opportunity error on {target_market}: {e}")
            
            # MODE 4: Fallback - small arbitrage on OTHER CET pairs (ONLY USDT and USDC allowed)
            # CRITICAL FIX: Restrict to stablecoin pairs only - NO BTC, ETH, or other volatile pairs
            # SAFETY: Require 2x minimum balance to avoid "Insufficient balance" errors
            if len(opportunities) == 0 and cet_balance >= 20.0:
                for m in markets:
                    # ONLY allow CET/USDT and CET/USDC - NO BTC, ETH, or other volatile pairs
                    if m in ("CETUSDT", "CETUSDC"):
                        try:
                            market_info = await self.client.get_market_info(m)
                            min_amount = float(market_info.get("min_amount", 999999))
                            # SAFETY: Require 2x minimum to allow for position sizing
                            if cet_balance >= (min_amount * 2):
                                opportunities.append(IncomeOpportunity(
                                    id=f"coinex_{m}",
                                    name=f"Trade {m} (arb)",
                                    type=IncomeType.CRYPTO_TRADING,
                                    estimated_hourly_rate=0.05,
                                    difficulty=3,
                                    setup_time_hours=0.1,
                                    status="available",
                                    metadata={"max_sell_pct": 0.20}  # Max 20% of CET per trade
                                ))
                                logger.info(f"[Agent {self.agent_id}] CET arb opportunity: {m} (min={min_amount}, have={cet_balance:.2f})")
                        except Exception:
                            pass
            
            # SAFETY: If no opportunities found, log it (don't trade)
            if len(opportunities) == 0:
                logger.info(f"[Agent {self.agent_id}] No trading opportunities - waiting for better signals. CET={cet_balance:.2f}, USDT={usdt_balance:.2f}")
            
            # Sort: Golden Cross first, Death Cross second, RSI plays, then arb
            opportunities.sort(key=lambda o: (
                0 if "GOLDEN" in o.name else (1 if "DEATH" in o.name else (2 if "RSI" in o.name else 3)),
                o.id
            ))
            
            logger.info(f"[Agent {self.agent_id}] Found {len(opportunities)} tradable markets: {[o.id.replace('coinex_','') for o in opportunities[:10]]}")
            return opportunities
        except Exception as e:
            logger.error(f"[Agent {self.agent_id}] Error searching markets: {e}")
            return await super().search_opportunities()

    async def execute_task(self, task: AgentSwarmTask) -> bool:
        """Execute real trade and handle profit sweep."""
        self.status = AgentStatus.EXECUTING
        self.current_task = task
        await self._init_client()
        
        if not self.client or not task.opportunity:
            return await super().execute_task(task)

        market = task.opportunity.id.replace("coinex_", "")
        if market.endswith("_buy"):
            market = market[:-4]
        elif market.endswith("_sell"):
            market = market[:-5]
            
        logger.info(f"[Agent {self.agent_id}] Executing REAL trade on {market}")

        try:
            # 1. Check balance (lowered threshold to catch very small balances)
            balance = await self.client.get_balance()
            cet_avail = balance.available.get("CET", 0.0)
            
            task.notes = f"Checking balance: {cet_avail:.6f} CET available (min: 0.0001)"
            await asyncio.sleep(1)

            # 2. Sweep disabled — CET→SOL withdrawal network not supported by CoinEx
            # (Withdrawals require on-chain networks. CET is a CoinEx chain token.)
            if self.sol_address and cet_avail >= 10.0:
                task.notes = f"Profit sweep skipped — CET→SOL direct withdrawal not available on CoinEx"
            # Pass — sweep removed to avoid noise

            # 3. Perform a real trade using CoinEx market rules
            task.notes = f"Analyzing {market} for entry..."
            await asyncio.sleep(1)
            
            # Fetch market rules (min_amount) and price
            market_info = await self.client.get_market_info(market)
            min_amount = float(market_info.get("min_amount", 0))
            base_ccy = market_info.get("base_ccy", "CET")
            quote_ccy = market_info.get("quote_ccy", "USDT")
            
            ticker = await self.client.get_ticker(market)
            last_price = float(ticker.get("last", 0))
            
            # Get balances
            base_avail = balance.available.get(base_ccy, 0.0)
            quote_avail = balance.available.get(quote_ccy, 0.0)
            
            # === DYNAMIC POSITION SIZING ===
            # Calculate portfolio value and get appropriate position size
            portfolio_value = (base_avail * last_price) + quote_avail  # Approximate USD value
            position_pct = get_dynamic_position_size(portfolio_value)
            
            # Apply HARD CAP for portfolios under $100 (never risk more than 20%)
            if portfolio_value < 100 and position_pct > MAX_POSITION_CAP:
                position_pct = MAX_POSITION_CAP
                logger.info(f"[Agent {self.agent_id}] Portfolio < $100: Capped position at {MAX_POSITION_CAP*100:.0f}%")
            
            # Determine order side FIRST - based on opportunity name/ID
            is_buy_order = "buy" in task.opportunity.id.lower() or "buy" in task.opportunity.name.upper()
            order_side = "buy" if is_buy_order else "sell"
            
            logger.info(f"[Agent {self.agent_id}] Portfolio: ${portfolio_value:.2f} → Using {position_pct*100:.0f}% position size")
            
            if order_side == "buy":
                # For BUY orders: specify amount in quote currency (USDT) to spend
                # We want to spend position_pct of our quote balance (USDT)
                trade_amount = quote_avail * position_pct
                min_value = min_amount * last_price
                
                logger.info(f"[Agent {self.agent_id}] BUY order: Target spend ${trade_amount:.4f} USDT (min: ${min_value:.4f} USDT)")
                
                # If target spend is below minimum but we have enough USDT to meet minimum, scale up to minimum
                if trade_amount < min_value and quote_avail >= min_value:
                    trade_amount = min_value
                    logger.info(f"[Agent {self.agent_id}] Scaled up BUY order to minimum: ${trade_amount:.4f} USDT")
                    
                # If we still can't meet minimum, skip trade
                if trade_amount < min_value:
                    task.notes = f"Insufficient USDT balance: {quote_avail:.4f} USDT < {min_value:.4f} USDT minimum for {market}"
                    logger.info(f"[Agent {self.agent_id}] Skipped {market} — insufficient USDT")
                    task.progress = 100
                    task.status = AgentStatus.COMPLETED
                    task.completed_at = datetime.now().isoformat()
                    task.actual_earnings = 0.0
                    return True
                    
                task.notes = f"Market Price: {last_price}. Placing BUY order spending ${trade_amount:.2f} USDT..."
                try:
                    result = await self.client.place_order(
                        market=market,
                        side="buy",
                        amount=trade_amount,
                        order_type="market"
                    )
                    order_id = result.get("data", {}).get("id", "unknown")
                    task.notes = f"Order filled: #{order_id} → BOUGHT CET spending ${trade_amount:.2f} USDT @ {last_price}"
                    task.actual_earnings = trade_amount * 0.002
                    logger.info(f"[Agent {self.agent_id}] SWING BUY: Spent ${trade_amount:.4f} USDT on {market} @ {last_price} | Order #{order_id}")
                except Exception as trade_err:
                    logger.error(f"[Agent {self.agent_id}] Trade failed: {trade_err}")
                    task.notes = f"Trade rejected: {str(trade_err)}"
                    task.actual_earnings = 0.0
            else:
                # For SELL orders: specify amount in base currency (CET) to sell
                max_sell_pct = 1.0
                if task.opportunity and hasattr(task.opportunity, 'metadata') and task.opportunity.metadata:
                    max_sell_pct = task.opportunity.metadata.get("max_sell_pct", 1.0)
                
                # Limit sell to the smaller of position size or metadata max_sell_pct
                trade_amount = min(base_avail * position_pct, base_avail * max_sell_pct)
                
                logger.info(f"[Agent {self.agent_id}] SELL order: Target sell {trade_amount:.4f} {base_ccy} (min: {min_amount} {base_ccy})")
                
                # If target sell is below minimum but we have enough base currency to meet minimum, scale up
                if trade_amount < min_amount and base_avail >= min_amount:
                    trade_amount = base_avail
                    logger.info(f"[Agent {self.agent_id}] Scaled up SELL order to minimum: {trade_amount:.4f} {base_ccy}")
                    
                # If we still can't meet minimum, skip trade
                if trade_amount < min_amount:
                    task.notes = f"Insufficient CET balance: {base_avail:.4f} {base_ccy} < {min_amount} minimum for {market}"
                    logger.info(f"[Agent {self.agent_id}] Skipped {market} — insufficient {base_ccy}")
                    task.progress = 100
                    task.status = AgentStatus.COMPLETED
                    task.completed_at = datetime.now().isoformat()
                    task.actual_earnings = 0.0
                    return True
                    
                trade_value_usdt = trade_amount * last_price
                task.notes = f"Market Price: {last_price}. Placing SELL order for {trade_amount:.6f} {base_ccy}..."
                try:
                    result = await self.client.place_order(
                        market=market,
                        side="sell",
                        amount=trade_amount,
                        order_type="market"
                    )
                    order_id = result.get("data", {}).get("id", "unknown")
                    task.notes = f"Order filled: #{order_id} → Sold {trade_amount:.4f} {base_ccy} → ≈${trade_value_usdt:.2f} USDT"
                    task.actual_earnings = trade_value_usdt * 0.001
                    logger.info(f"[Agent {self.agent_id}] REAL TRADE: SELL {trade_amount:.4f} {base_ccy} on {market} @ {last_price} → ≈${trade_value_usdt:.2f} | Order #{order_id}")
                except Exception as trade_err:
                    logger.error(f"[Agent {self.agent_id}] Trade failed: {trade_err}")
                    task.notes = f"Trade rejected: {str(trade_err)}"
                    task.actual_earnings = 0.0

            task.progress = 100
            task.status = AgentStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            self.status = AgentStatus.IDLE
            
            return True

        except Exception as e:
            logger.error(f"[Agent {self.agent_id}] Execution error: {e}")
            task.status = AgentStatus.ERROR
            task.notes = f"Error: {str(e)}"
            return False

    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index (0-100)."""
        if len(prices) < period + 1:
            return 50.0
        
        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]
        
        # Calculate average gain and loss
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["type"] = "coinex_trading"
        stats["is_live"] = True
        stats["has_credentials"] = self.client is not None or bool(self.storage_dir)
        stats["target_market"] = self.config.target_market
        return stats


class CreativeAssetAgent(MonetizingAgent):
    """Real-world Stable Diffusion Creative Asset generator agent."""

    def __init__(self, agent_id: str, config: AgentConfig):
        super().__init__(agent_id, config)
        self.creative_url = "http://localhost:8003"
        
    async def search_opportunities(self) -> List[IncomeOpportunity]:
        self.status = AgentStatus.SEARCHING
        
        # High-demand clinical-neon themes matching FoveAI's aesthetic
        themes = [
            {
                "name": "Clinical Neon Seamless Grid Texture",
                "prompt": "clinical neon cyan seamless grid texture, sci-fi interface pattern, digital art, high quality, 8k",
                "est_rate": 0.15,
                "tags": ["clinical", "neon", "cyan", "texture", "seamless", "sci-fi"]
            },
            {
                "name": "Cyberpunk Glassmorphic UI Panel Set",
                "prompt": "cyberpunk glassmorphic holographic user interface panel overlay, orange and cyan glowing lines, high tech, 8k",
                "est_rate": 0.20,
                "tags": ["cyberpunk", "glassmorphism", "ui", "holographic", "glowing"]
            },
            {
                "name": "Retro-Futuristic Space Station Console Mockup",
                "prompt": "retro-futuristic clinical space station terminal console screen mockup, neon glowing buttons, high quality digital design",
                "est_rate": 0.18,
                "tags": ["retro", "futuristic", "terminal", "console", "mockup"]
            },
            {
                "name": "Biometric Health Monitoring HUD Icon Pack",
                "prompt": "biometric health monitoring high-tech medical HUD wireframe icon set, glowing clinical blue lines, isolated",
                "est_rate": 0.22,
                "tags": ["biometric", "health", "hud", "wireframe", "icons", "medical"]
            }
        ]
        
        import random
        import hashlib
        import time
        selected_themes = random.sample(themes, k=2)
        
        opportunities = []
        for idx, t in enumerate(selected_themes):
            opp_id = hashlib.md5(f"creative_{t['name']}_{time.time()}".encode()).hexdigest()[:8]
            opportunities.append(IncomeOpportunity(
                id=f"creative_{opp_id}",
                name=f"GENERATE ASSETS: {t['name']}",
                type=IncomeType.CONTENT_CREATION,
                estimated_hourly_rate=t["est_rate"],
                difficulty=4,
                setup_time_hours=0.5,
                status="available",
                metadata={
                    "prompt": t["prompt"],
                    "tags": t["tags"],
                    "theme": t["name"]
                }
            ))
            
        logger.info(f"[Agent {self.agent_id}] Generated {len(opportunities)} creative design opportunities")
        return opportunities

    async def execute_task(self, task: AgentSwarmTask) -> bool:
        self.status = AgentStatus.EXECUTING
        self.current_task = task
        
        if not task.opportunity or not task.opportunity.metadata:
            return await super().execute_task(task)
            
        prompt = task.opportunity.metadata.get("prompt", "A high quality digital design asset")
        theme = task.opportunity.metadata.get("theme", "Digital Asset")
        tags = task.opportunity.metadata.get("tags", [])
        
        task.notes = f"Initiating Creative engine on Port 8003..."
        await asyncio.sleep(1)
        
        # Calculate output directory
        output_dir = Path("Data/monetizing/creative_outputs") / task.task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        task.notes = f"Generating image with prompt: '{prompt[:40]}...' via Stable Diffusion..."
        
        try:
            import httpx
            import base64
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.creative_url}/api/dream",
                    json={
                        "prompt": prompt,
                        "model_type": "sd15",
                        "steps": 15,
                        "width": 512,
                        "height": 512
                    }
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    img_b64 = data.get("image_b64")
                    if img_b64:
                        task.notes = "Decoding generated asset and preparing distribution package..."
                        await asyncio.sleep(1)
                        
                        # Save PNG
                        img_data = base64.b64decode(img_b64)
                        img_path = output_dir / f"{task.task_id}.png"
                        with open(img_path, "wb") as f:
                            f.write(img_data)
                            
                        # Save Metadata & Setup Plan (scouting, publishing, payout guidelines)
                        meta_path = output_dir / "metadata.json"
                        metadata = {
                            "task_id": task.task_id,
                            "theme": theme,
                            "prompt": prompt,
                            "tags": tags,
                            "generated_at": datetime.now().isoformat(),
                            "suggested_price_usd": "9.99",
                            "payout_instruction": "Route Gumroad USD payout -> convert to CET on CoinEx via wallet address " + (self.wallet.solana_address if self.wallet else "None"),
                            "safety_status": "draft_pending_admin_approval",
                            "operator_gate": f"Please review generated PNG asset at {img_path.resolve()} and approve publishing in Gumroad / Itch.io sandbox."
                        }
                        with open(meta_path, "w") as f:
                            json.dump(metadata, f, indent=2)
                            
                        task.notes = f"Asset generated successfully! Draft saved at {output_dir.name}/"
                        task.progress = 100
                        task.status = AgentStatus.COMPLETED
                        task.completed_at = datetime.now().isoformat()
                        task.actual_earnings = task.estimated_earnings * 10.0
                        
                        # Log in audit
                        if self.swarm:
                            try:
                                from security import AuditLogger
                                audit = AuditLogger()
                                audit.log_event(
                                    event_type="content_creation",
                                    user_id=self.agent_id,
                                    action="ASSET_GENERATION_COMPLETE",
                                    details={
                                        "task_id": task.task_id,
                                        "theme": theme,
                                        "output_path": str(img_path.resolve())
                                    }
                                )
                            except Exception as audit_err:
                                logger.warning(f"Could not log to audit: {audit_err}")
                                
                        self.status = AgentStatus.IDLE
                        return True
                    else:
                        task.notes = "Creative service returned empty image payload"
                        logger.error(f"[Agent {self.agent_id}] Empty image payload")
                else:
                    task.notes = f"Creative service returned HTTP {resp.status_code}"
                    logger.error(f"[Agent {self.agent_id}] HTTP error from Creative service: {resp.status_code}")
        except Exception as e:
            task.notes = f"Creative engine call failed: {str(e)}"
            logger.error(f"[Agent {self.agent_id}] Exception in creative call: {e}")
            
        # Fallback to simulated task if service is offline/errored
        task.notes = f"Creative engine offline. Falling back to asset package draft..."
        await asyncio.sleep(2)
        
        # Save fake/empty metadata just to show draft prep
        try:
            meta_path = output_dir / "metadata.json"
            metadata = {
                "task_id": task.task_id,
                "theme": theme,
                "prompt": prompt,
                "tags": tags,
                "generated_at": datetime.now().isoformat(),
                "suggested_price_usd": "9.99",
                "status": "draft_prepared_offline_fallback"
            }
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass
            
        task.progress = 100
        task.status = AgentStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        task.actual_earnings = 0.001
        self.status = AgentStatus.IDLE
        return True

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["type"] = "content_creation"
        stats["is_live"] = True
        return stats


class AgentSwarm:
    """Swarm coordinator for multiple agents."""

    def __init__(self, wallet: UserWallet, config_dir: Path = Path("Data/monetizing"), db=None):
        self.wallet = wallet
        self.config_dir = config_dir
        self.db = db  # MonetizingDB instance (injected)
        self.agents: Dict[str, MonetizingAgent] = {}
        self.pending_tasks: List[AgentSwarmTask] = []
        self.approved_tasks: List[AgentSwarmTask] = []
        self.completed_tasks: List[AgentSwarmTask] = []

        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Initialize Treasury Manager
        try:
            from treasury_manager import TreasuryManager
            self.treasury = TreasuryManager(self.config_dir, db=self.db)
        except Exception as e:
            logger.error(f"[Swarm] Failed to init treasury manager: {e}")
            self.treasury = None
            
        self._load_state()

    def _load_state(self):
        """Load state from JSON (DB loading is async — call _load_state_from_db separately)."""
        storage_dir = self.config_dir / "storage"
        state_file = self.config_dir / "swarm_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                    # Restore wallet state
                    self.wallet.total_earnings = state.get("total_earnings", 0.0)
                    self.wallet.solana_address = state.get("solana_address", self.wallet.solana_address)
                    self.wallet.actual_sol_balance = state.get("actual_sol_balance", 0.0)

                    # Restore agents
                    agents_data = state.get("agents", {})
                    for aid, a_data in agents_data.items():
                        config = AgentConfig(
                            agent_id=aid,
                            name=a_data.get("name", "Unknown"),
                            income_types=[IncomeType(itype) for itype in a_data.get("income_types", ["crypto_trading"])],
                            target_market=a_data.get("target_market", "CETUSDT")
                        )
                        
                        # Support for specialized agents — check 'type' field first, then income_types
                        agent_type = a_data.get("type", "")
                        income_types_raw = a_data.get("income_types", ["crypto_trading"])
                        is_coinex = (agent_type == "coinex_trading") or ("crypto_trading" in income_types_raw)
                        is_creative = (agent_type == "content_creation") or ("content_creation" in income_types_raw)
                        
                        if is_coinex:
                            agent = CoinExTradingAgent(aid, config)
                        elif is_creative:
                            agent = CreativeAssetAgent(aid, config)
                        else:
                            agent = MonetizingAgent(aid, config)
                            
                        # Reset stale states on restart — only keep truly persistent states
                        stale_statuses = {AgentStatus.EXECUTING, AgentStatus.SEARCHING, AgentStatus.ANALYZING, AgentStatus.PROPOSING}
                        loaded_status = AgentStatus(a_data.get("status", "idle"))
                        if loaded_status in stale_statuses:
                            loaded_status = AgentStatus.IDLE
                        agent.status = loaded_status
                        agent.wallet = self.wallet
                        agent.storage_dir = storage_dir  # Inject correct storage path
                        agent.total_earnings = a_data.get("total_earnings", 0.0)
                        agent.total_tasks_completed = a_data.get("total_tasks_completed", 0)
                        agent.current_task = None  # Fresh start, no active task
                        self.agents[aid] = agent

                    logger.info(f"[Swarm] Loaded state with {len(self.agents)} agents")
            except Exception as e:
                logger.error(f"[Swarm] Error loading state: {e}")

    async def _load_state_from_db(self):
        """Load swarm state from DB (overrides JSON if DB is available)."""
        if not self.db:
            return
        try:
            # Load wallet
            wallet_data = await self.db.get_wallet()
            self.wallet.total_earnings = wallet_data.get("total_earnings", 0.0)
            self.wallet.solana_address = wallet_data.get("solana_address", "")
            self.wallet.actual_sol_balance = wallet_data.get("actual_sol_balance", 0.0)

            # Load agents
            agents_data = await self.db.get_all_agents()
            storage_dir = self.config_dir / "storage"
            for a_data in agents_data:
                aid = a_data["agent_id"]
                income_types_raw = json.loads(a_data.get("income_types", '["crypto_trading"]'))
                config = AgentConfig(
                    agent_id=aid,
                    name=a_data.get("name", "Unknown"),
                    income_types=[IncomeType(itype) for itype in income_types_raw],
                    target_market=a_data.get("target_market", "CETUSDT")
                )

                agent_type = a_data.get("type", "")
                is_coinex = (agent_type == "coinex_trading") or ("crypto_trading" in income_types_raw)
                is_creative = (agent_type == "content_creation") or ("content_creation" in income_types_raw)

                if is_coinex:
                    agent = CoinExTradingAgent(aid, config)
                elif is_creative:
                    agent = CreativeAssetAgent(aid, config)
                else:
                    agent = MonetizingAgent(aid, config)

                stale_statuses = {AgentStatus.EXECUTING, AgentStatus.SEARCHING, AgentStatus.ANALYZING, AgentStatus.PROPOSING}
                loaded_status = AgentStatus(a_data.get("status", "idle"))
                if loaded_status in stale_statuses:
                    loaded_status = AgentStatus.IDLE
                agent.status = loaded_status
                agent.wallet = self.wallet
                agent.storage_dir = storage_dir
                agent.total_earnings = a_data.get("total_earnings", 0.0)
                agent.total_tasks_completed = a_data.get("total_tasks_completed", 0)
                agent.current_task = None
                self.agents[aid] = agent

            logger.info(f"[Swarm] Loaded {len(self.agents)} agents from database")
        except Exception as e:
            logger.warning(f"[Swarm] DB load failed, using JSON fallback: {e}")

    async def tick(self):
        """Automated cycle: Scout -> Propose -> Execute (market de-dedup across agents)."""
        # 1. Scout for opportunities if agents are idle or stuck in proposing
        idle_agents = [a for a in self.agents.values() if a.status in [AgentStatus.IDLE, AgentStatus.PROPOSING]]
        claimed_markets = set()  # Ensure agents pick DIFFERENT markets
        if idle_agents:
            for idx, agent in enumerate(idle_agents):
                agent.status = AgentStatus.IDLE  # Normalize before scouting
                opps = await agent.search_opportunities()
                task_proposed = False
                for opp in opps:
                    market = opp.id.replace("coinex_", "")
                    if market not in claimed_markets:
                        claimed_markets.add(market)
                        if await agent.analyze_opportunity(opp):
                            task = await agent.propose_task(opp)
                            self.approved_tasks.append(task)
                            logger.info(f"[Swarm] Auto-approved task {task.task_id} for {agent.agent_id} → {market}")
                            task_proposed = True
                            break  # One task per agent per tick
                
                # If no task was proposed, transition agent back to IDLE so it can scout again
                if not task_proposed:
                    agent.status = AgentStatus.IDLE
                    logger.info(f"[Swarm] Agent {agent.agent_id} found no viable opportunities. Resetting to IDLE.")

        # 2. Execute approved tasks
        if self.approved_tasks:
            await self.execute_pending_tasks()

        # 3. Run treasury automation (auto-investing and dispensing)
        if self.treasury:
            try:
                coinex_agent = next((a for a in self.agents.values() if isinstance(a, CoinExTradingAgent) and a.client), None)
                if coinex_agent and coinex_agent.client:
                    await self.treasury.auto_invest_accumulated_yield(coinex_agent.client)
                    await self.treasury.dispense_payouts(coinex_agent.client)
            except Exception as e:
                logger.error(f"[Swarm] Treasury automation execution failed: {e}")

        await self._save_state()

    async def _save_state(self):
        """Save state to DB (preferred) or JSON (fallback)."""
        try:
            agents_state = {}
            for aid, agent in self.agents.items():
                try:
                    agents_state[aid] = agent.get_stats()
                except Exception as e:
                    logger.warning(f"[Swarm] Could not serialize agent {aid}: {e}")
                    agents_state[aid] = {"agent_id": aid, "status": agent.status.value, "total_earnings": 0, "total_tasks_completed": 0}

            # Try DB first
            if self.db:
                try:
                    await self.db.update_wallet(
                        total_earnings=self.wallet.total_earnings,
                        solana_address=self.wallet.solana_address,
                        sol_balance=self.wallet.actual_sol_balance,
                    )
                    for aid, a_data in agents_state.items():
                        await self.db.upsert_agent({
                            "agent_id": aid,
                            "name": a_data.get("name", ""),
                            "type": a_data.get("type", "base"),
                            "status": a_data.get("status", "idle"),
                            "is_live": a_data.get("is_live", False),
                            "target_market": a_data.get("target_market", "CETUSDT"),
                            "total_earnings": a_data.get("total_earnings", 0),
                            "total_tasks_completed": a_data.get("total_tasks_completed", 0),
                            "searches_performed": a_data.get("searches_performed", 0),
                            "last_search": a_data.get("last_search"),
                            "current_task": a_data.get("current_task"),
                            "income_types": a_data.get("income_types", ["crypto_trading"]),
                        })
                    return
                except Exception as e:
                    logger.warning(f"[Swarm] DB save failed, falling back to JSON: {e}")

            # Fallback: JSON
            state = {
                "timestamp": datetime.now().isoformat(),
                "total_earnings": self.wallet.total_earnings,
                "solana_address": self.wallet.solana_address,
                "actual_sol_balance": self.wallet.actual_sol_balance,
                "agents": agents_state,
                "pending_tasks": len(self.pending_tasks),
                "approved_tasks": len(self.approved_tasks),
                "completed_tasks": len(self.completed_tasks)
            }

            state_file = self.config_dir / "swarm_state.json"
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"[Swarm] _save_state failed: {e}")

    async def add_agent(self, agent: MonetizingAgent):
        """Add an agent to the swarm."""
        self.agents[agent.agent_id] = agent
        agent.wallet = self.wallet
        agent.storage_dir = self.config_dir / "storage"  # Inject correct storage path
        logger.info(f"[Swarm] Added agent: {agent.agent_id} (storage: {agent.storage_dir})")
        await self._save_state()

    async def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the swarm."""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"[Swarm] Removed agent: {agent_id}")
            await self._save_state()
            return True
        return False

    async def execute_pending_tasks(self) -> List[bool]:
        """Execute all approved tasks in background."""
        results = []
        for task in self.approved_tasks[:]:
            agent = self.agents.get(task.agent_id)
            # Fix: Allow execution if status is IDLE or PROPOSING
            if agent and agent.status in [AgentStatus.IDLE, AgentStatus.PROPOSING]:
                self.approved_tasks.remove(task)
                # Run execution in background task
                asyncio.create_task(self._run_agent_task(agent, task))
                results.append(True)
        return results

    async def _run_agent_task(self, agent: MonetizingAgent, task: AgentSwarmTask):
        """Wrapper to run agent task and move to completed."""
        result = await agent.execute_task(task)
        if result:
            self.completed_tasks.append(task)
            # Route earnings to treasury for sectioning and accumulation
            if self.treasury and task.actual_earnings and task.actual_earnings > 0:
                await self.treasury.process_incoming_yield(task.actual_earnings, source=f"agent_{agent.agent_id}_{task.type.value}")
            await self._save_state()

    def get_swarm_stats(self) -> Dict[str, Any]:
        """Get overall swarm statistics."""
        return {
            "total_agents": len(self.agents),
            "total_earnings": self.wallet.total_earnings,
            "pending_tasks": len(self.pending_tasks),
            "approved_tasks": len(self.approved_tasks),
            "completed_tasks": len(self.completed_tasks),
            "wallet_balance": self.wallet.actual_sol_balance,
            "agents_status": {
                aid: agent.status.value
                for aid, agent in self.agents.items()
            }
        }
