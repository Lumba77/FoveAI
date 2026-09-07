"""
FoveAI Monetizing Database — SQLite persistence layer
=====================================================
Replaces flat JSON files with a WAL-mode SQLite database for:
  - Crash-safe atomic writes (3 concurrent agents won't corrupt)
  - Queryable trade history (slice by agent, pair, date range)
  - OHLCV candle cache (avoid re-fetching CoinEx klines)
  - LLM mentor context (query last N trades, filter by win/loss)

Usage:
    db = await MonetizingDB.create("Data/monetizing/monetizing.db")
    # ... use db ...
    await db.close()

All methods are async (aiosqlite). WAL mode enables safe concurrent writes.
"""

import aiosqlite
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("monetizing_db")

SCHEMA = """
-- ============================================================
-- TRADES — every buy/sell executed by any agent
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    pair            TEXT NOT NULL,       -- e.g. "CETUSDT"
    side            TEXT NOT NULL,       -- "buy" | "sell"
    order_type      TEXT NOT NULL DEFAULT 'market',
    amount          REAL NOT NULL,       -- base asset quantity
    price           REAL NOT NULL,       -- execution price
    usdt_value      REAL NOT NULL,       -- total USDT value
    profit_usdt     REAL    DEFAULT 0,
    profit_pct      REAL    DEFAULT 0,
    reason          TEXT    DEFAULT '',
    paper           INTEGER DEFAULT 1,   -- 1=paper, 0=real
    mentor_reviewed INTEGER DEFAULT 0,
    created_at      TEXT    NOT NULL,    -- ISO timestamp
    synced          INTEGER DEFAULT 0    -- 1 after JSON migration
);

CREATE INDEX IF NOT EXISTS idx_trades_agent ON trades(agent_id);
CREATE INDEX IF NOT EXISTS idx_trades_pair   ON trades(pair);
CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(created_at);

-- ============================================================
-- AGENTS — current state of each monetizing agent
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,
    name            TEXT    DEFAULT '',
    type            TEXT    DEFAULT 'coinex_trading',
    status          TEXT    DEFAULT 'idle',
    is_live         INTEGER DEFAULT 0,
    target_market   TEXT    DEFAULT 'CETUSDT',
    total_earnings  REAL    DEFAULT 0,
    total_tasks_completed INTEGER DEFAULT 0,
    searches_performed    INTEGER DEFAULT 0,
    last_search     TEXT,
    current_task    TEXT,
    income_types    TEXT    DEFAULT '["crypto_trading"]',  -- JSON array
    updated_at      TEXT    NOT NULL
);

-- ============================================================
-- PORTFOLIOS — paper/real portfolio snapshots per agent
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolios (
    agent_id        TEXT NOT NULL,
    usdt_balance    REAL    DEFAULT 0,
    holdings        TEXT    DEFAULT '{}',  -- JSON: {"CET": 123.4}
    starting_usdt   REAL    DEFAULT 20.0,
    total_pnl       REAL    DEFAULT 0,
    win_count       INTEGER DEFAULT 0,
    loss_count      INTEGER DEFAULT 0,
    updated_at      TEXT    NOT NULL,
    PRIMARY KEY (agent_id)
);

-- ============================================================
-- TREASURY — yield accumulation and sectioning
-- ============================================================
CREATE TABLE IF NOT EXISTS treasury (
    id              INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    accumulated_grinding   REAL DEFAULT 0,
    accumulated_reserve    REAL DEFAULT 0,
    accumulated_dispense   REAL DEFAULT 0,
    total_yield_accumulated REAL DEFAULT 0,
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- TREASURY SETTINGS — allocation percentages and thresholds
-- ============================================================
CREATE TABLE IF NOT EXISTS treasury_settings (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    grinding_swarm_pct      REAL DEFAULT 0.40,
    safeguard_reserve_pct   REAL DEFAULT 0.30,
    dispense_payout_pct     REAL DEFAULT 0.30,
    min_reinvest_amount_usd REAL DEFAULT 2.0,
    min_dispense_amount_usd REAL DEFAULT 10.0,
    payout_address          TEXT DEFAULT '',
    payout_network          TEXT DEFAULT 'SOL',
    updated_at              TEXT NOT NULL
);

-- ============================================================
-- OHLCV CACHE — cached kline/candlestick data from CoinEx
-- ============================================================
CREATE TABLE IF NOT EXISTS ohlcv_cache (
    symbol      TEXT NOT NULL,
    period      TEXT NOT NULL,      -- "1min", "5min", "1hour", etc.
    open_time   TEXT NOT NULL,      -- candle open timestamp
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (symbol, period, open_time)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_time ON ohlcv_cache(symbol, period, open_time);

-- ============================================================
-- TRAINING SESSIONS — swarm training logs
-- ============================================================
CREATE TABLE IF NOT EXISTS training_sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    strategy     TEXT DEFAULT 'Golden Cross EMA-50/200',
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades  INTEGER DEFAULT 0,
    overall_win_rate REAL DEFAULT 0,
    total_pnl    REAL DEFAULT 0,
    best_agent   TEXT,
    worst_agent  TEXT,
    largest_win  REAL DEFAULT 0,
    largest_loss REAL DEFAULT 0,
    per_pair     TEXT DEFAULT '{}',  -- JSON
    agent_stats  TEXT DEFAULT '{}'   -- JSON
);

-- ============================================================
-- WALLET — global wallet state (singleton)
-- ============================================================
CREATE TABLE IF NOT EXISTS wallet (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    total_earnings    REAL DEFAULT 0,
    solana_address    TEXT DEFAULT '',
    actual_sol_balance REAL DEFAULT 0,
    updated_at        TEXT NOT NULL
);

-- ============================================================
-- AUDIT LOG — append-only event log
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,       -- "trade", "treasury", "agent", etc.
    agent_id    TEXT,
    action      TEXT NOT NULL,
    details     TEXT DEFAULT '{}',   -- JSON blob
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type, created_at);
"""


class MonetizingDB:
    """Async SQLite database for FoveAI monetizing system."""

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).resolve())
        self._db: Optional[aiosqlite.Connection] = None

    @classmethod
    async def create(cls, db_path: str = "Data/monetizing/monetizing.db") -> "MonetizingDB":
        """Create and initialize the database."""
        instance = cls(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        instance._db = await aiosqlite.connect(instance.db_path)
        # Enable WAL for concurrent writes
        await instance._db.execute("PRAGMA journal_mode=WAL")
        await instance._db.execute("PRAGMA synchronous=NORMAL")
        await instance._db.executescript(SCHEMA)
        await instance._db.commit()
        logger.info(f"[DB] Initialized {db_path} (WAL mode)")
        return instance

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("[DB] Connection closed")

    # ----------------------------------------------------------------
    # TRADES
    # ----------------------------------------------------------------

    async def insert_trade(self, trade: Dict[str, Any]) -> str:
        """Insert a single trade. Returns trade_id."""
        await self._db.execute(
            """INSERT OR REPLACE INTO trades
               (trade_id, agent_id, pair, side, order_type, amount, price,
                usdt_value, profit_usdt, profit_pct, reason, paper,
                mentor_reviewed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade["trade_id"], trade["agent_id"], trade["pair"],
                trade["side"], trade.get("order_type", "market"),
                trade["amount"], trade["price"], trade["usdt_value"],
                trade.get("profit_usdt", 0), trade.get("profit_pct", 0),
                trade.get("reason", ""), int(trade.get("paper", True)),
                int(trade.get("mentor_reviewed", False)),
                trade.get("timestamp", datetime.now().isoformat()),
            ),
        )
        await self._db.commit()
        return trade["trade_id"]

    async def get_trades(
        self,
        agent_id: Optional[str] = None,
        pair: Optional[str] = None,
        side: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
        paper_only: Optional[bool] = None,
    ) -> List[Dict]:
        """Query trades with flexible filters."""
        clauses = []
        params = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if pair:
            clauses.append("pair = ?")
            params.append(pair)
        if side:
            clauses.append("side = ?")
            params.append(side)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        if paper_only is not None:
            clauses.append("paper = ?")
            params.append(int(paper_only))

        where = " AND ".join(clauses) if clauses else "1=1"
        params.append(limit)
        query = f"SELECT * FROM trades WHERE {where} ORDER BY created_at DESC LIMIT ?"

        rows = await self._db.execute_fetchall(query, params)
        columns = [desc[0] for desc in rows.description] if rows else []
        return [dict(zip(columns, row)) for row in rows]

    async def get_trade_stats(self, agent_id: Optional[str] = None) -> Dict:
        """Aggregate trade statistics."""
        where = "WHERE agent_id = ?" if agent_id else ""
        params = [agent_id] if agent_id else []

        row = await self._db.execute_fetchall(
            f"""SELECT COUNT(*) as total_trades,
                       SUM(CASE WHEN profit_usdt > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN profit_usdt <= 0 THEN 1 ELSE 0 END) as losses,
                       COALESCE(SUM(profit_usdt), 0) as total_pnl,
                       COALESCE(MAX(profit_usdt), 0) as largest_win,
                       COALESCE(MIN(profit_usdt), 0) as largest_loss
                FROM trades {where}""",
            params,
        )
        if row:
            cols = [desc[0] for desc in row.description]
            result = dict(zip(cols, row[0]))
            total = result.get("total_trades", 0)
            result["win_rate"] = (result.get("wins", 0) / total * 100) if total > 0 else 0
            return result
        return {}

    async def mark_mentor_reviewed(self, trade_ids: List[str]):
        """Mark trades as reviewed by the LLM mentor."""
        if not trade_ids:
            return
        placeholders = ",".join("?" * len(trade_ids))
        await self._db.execute(
            f"UPDATE trades SET mentor_reviewed = 1 WHERE trade_id IN ({placeholders})",
            trade_ids,
        )
        await self._db.commit()

    # ----------------------------------------------------------------
    # AGENTS
    # ----------------------------------------------------------------

    async def upsert_agent(self, agent: Dict[str, Any]):
        """Insert or update an agent's state."""
        income_types = agent.get("income_types", ["crypto_trading"])
        if isinstance(income_types, list):
            income_types = json.dumps(income_types)

        await self._db.execute(
            """INSERT OR REPLACE INTO agents
               (agent_id, name, type, status, is_live, target_market,
                total_earnings, total_tasks_completed, searches_performed,
                last_search, current_task, income_types, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent["agent_id"], agent.get("name", ""), agent.get("type", "coinex_trading"),
                agent.get("status", "idle"), int(agent.get("is_live", False)),
                agent.get("target_market", "CETUSDT"),
                agent.get("total_earnings", 0), agent.get("total_tasks_completed", 0),
                agent.get("searches_performed", 0), agent.get("last_search"),
                agent.get("current_task"), income_types,
                datetime.now().isoformat(),
            ),
        )
        await self._db.commit()

    async def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get a single agent's state."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        )
        if rows:
            cols = [desc[0] for desc in rows.description]
            return dict(zip(cols, rows[0]))
        return None

    async def get_all_agents(self) -> List[Dict]:
        """Get all agents."""
        rows = await self._db.execute_fetchall("SELECT * FROM agents")
        if rows:
            cols = [desc[0] for desc in rows.description]
            return [dict(zip(cols, row)) for row in rows]
        return []

    async def delete_agent(self, agent_id: str):
        """Remove an agent."""
        await self._db.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
        await self._db.commit()

    # ----------------------------------------------------------------
    # PORTFOLIOS
    # ----------------------------------------------------------------

    async def upsert_portfolio(self, portfolio: Dict[str, Any]):
        """Insert or update a portfolio."""
        holdings = portfolio.get("holdings", {})
        if isinstance(holdings, dict):
            holdings = json.dumps(holdings)

        await self._db.execute(
            """INSERT OR REPLACE INTO portfolios
               (agent_id, usdt_balance, holdings, starting_usdt,
                total_pnl, win_count, loss_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                portfolio["agent_id"], portfolio.get("usdt_balance", 0),
                holdings, portfolio.get("starting_usdt", 20.0),
                portfolio.get("total_pnl", 0), portfolio.get("win_count", 0),
                portfolio.get("loss_count", 0), datetime.now().isoformat(),
            ),
        )
        await self._db.commit()

    async def get_portfolio(self, agent_id: str) -> Optional[Dict]:
        """Get a single portfolio."""
        rows = await self._db.execute_fetchall(
            "SELECT * FROM portfolios WHERE agent_id = ?", (agent_id,)
        )
        if rows:
            cols = [desc[0] for desc in rows.description]
            d = dict(zip(cols, rows[0]))
            d["holdings"] = json.loads(d.get("holdings", "{}"))
            return d
        return None

    async def get_all_portfolios(self) -> List[Dict]:
        rows = await self._db.execute_fetchall("SELECT * FROM portfolios")
        if rows:
            cols = [desc[0] for desc in rows.description]
            results = []
            for row in rows:
                d = dict(zip(cols, row))
                d["holdings"] = json.loads(d.get("holdings", "{}"))
                results.append(d)
            return results
        return []

    # ----------------------------------------------------------------
    # TREASURY
    # ----------------------------------------------------------------

    async def get_treasury(self) -> Dict:
        """Get treasury state (creates defaults if missing)."""
        rows = await self._db.execute_fetchall("SELECT * FROM treasury WHERE id = 1")
        if rows:
            cols = [desc[0] for desc in rows.description]
            return dict(zip(cols, rows[0]))
        # Insert defaults
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT INTO treasury (id, accumulated_grinding, accumulated_reserve,
               accumulated_dispense, total_yield_accumulated, updated_at)
               VALUES (1, 0, 0, 0, 0, ?)""",
            (now,),
        )
        await self._db.commit()
        return {
            "id": 1, "accumulated_grinding": 0, "accumulated_reserve": 0,
            "accumulated_dispense": 0, "total_yield_accumulated": 0, "updated_at": now,
        }

    async def update_treasury(self, grinding: float, reserve: float, dispense: float, total_yield: float):
        """Update treasury balances."""
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT OR REPLACE INTO treasury
               (id, accumulated_grinding, accumulated_reserve, accumulated_dispense,
                total_yield_accumulated, updated_at)
               VALUES (1, ?, ?, ?, ?, ?)""",
            (grinding, reserve, dispense, total_yield, now),
        )
        await self._db.commit()

    async def get_treasury_settings(self) -> Dict:
        rows = await self._db.execute_fetchall("SELECT * FROM treasury_settings WHERE id = 1")
        if rows:
            cols = [desc[0] for desc in rows.description]
            return dict(zip(cols, rows[0]))
        # Insert defaults
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT INTO treasury_settings
               (id, grinding_swarm_pct, safeguard_reserve_pct, dispense_payout_pct,
                min_reinvest_amount_usd, min_dispense_amount_usd, payout_address,
                payout_network, updated_at)
               VALUES (1, 0.40, 0.30, 0.30, 2.0, 10.0, '', 'SOL', ?)""",
            (now,),
        )
        await self._db.commit()
        return {
            "id": 1, "grinding_swarm_pct": 0.40, "safeguard_reserve_pct": 0.30,
            "dispense_payout_pct": 0.30, "min_reinvest_amount_usd": 2.0,
            "min_dispense_amount_usd": 10.0, "payout_address": "",
            "payout_network": "SOL", "updated_at": now,
        }

    async def update_treasury_settings(self, settings: Dict):
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT OR REPLACE INTO treasury_settings
               (id, grinding_swarm_pct, safeguard_reserve_pct, dispense_payout_pct,
                min_reinvest_amount_usd, min_dispense_amount_usd, payout_address,
                payout_network, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                settings.get("grinding_swarm_pct", 0.40),
                settings.get("safeguard_reserve_pct", 0.30),
                settings.get("dispense_payout_pct", 0.30),
                settings.get("min_reinvest_amount_usd", 2.0),
                settings.get("min_dispense_amount_usd", 10.0),
                settings.get("payout_address", ""),
                settings.get("payout_network", "SOL"),
                now,
            ),
        )
        await self._db.commit()

    # ----------------------------------------------------------------
    # WALLET
    # ----------------------------------------------------------------

    async def get_wallet(self) -> Dict:
        rows = await self._db.execute_fetchall("SELECT * FROM wallet WHERE id = 1")
        if rows:
            cols = [desc[0] for desc in rows.description]
            return dict(zip(cols, rows[0]))
        now = datetime.now().isoformat()
        await self._db.execute(
            "INSERT INTO wallet (id, total_earnings, solana_address, actual_sol_balance, updated_at) VALUES (1, 0, '', 0, ?)",
            (now,),
        )
        await self._db.commit()
        return {"id": 1, "total_earnings": 0, "solana_address": "", "actual_sol_balance": 0, "updated_at": now}

    async def update_wallet(self, total_earnings: float, solana_address: str = "", sol_balance: float = 0):
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT OR REPLACE INTO wallet (id, total_earnings, solana_address, actual_sol_balance, updated_at)
               VALUES (1, ?, ?, ?, ?)""",
            (total_earnings, solana_address, sol_balance, now),
        )
        await self._db.commit()

    # ----------------------------------------------------------------
    # OHLCV CACHE
    # ----------------------------------------------------------------

    async def cache_ohlcv(self, symbol: str, period: str, candles: List[Dict]):
        """Bulk-insert kline candles. Existing candles are replaced by primary key."""
        now = datetime.now().isoformat()
        rows = []
        for c in candles:
            open_time = c.get("created_at", c.get("time", c.get("open_time", now)))
            rows.append((
                symbol, period, open_time,
                float(c.get("open", c.get("open_price", 0))),
                float(c.get("high", 0)),
                float(c.get("low", 0)),
                float(c.get("close", 0)),
                float(c.get("volume", 0)),
                now,
            ))
        await self._db.executemany(
            """INSERT OR REPLACE INTO ohlcv_cache
               (symbol, period, open_time, open, high, low, close, volume, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()

    async def get_ohlcv(self, symbol: str, period: str, since: Optional[str] = None, limit: int = 500) -> List[Dict]:
        """Get cached candles for a symbol/period."""
        if since:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM ohlcv_cache
                   WHERE symbol = ? AND period = ? AND open_time >= ?
                   ORDER BY open_time ASC LIMIT ?""",
                (symbol, period, since, limit),
            )
        else:
            rows = await self._db.execute_fetchall(
                """SELECT * FROM ohlcv_cache
                   WHERE symbol = ? AND period = ?
                   ORDER BY open_time DESC LIMIT ?""",
                (symbol, period, limit),
            )
        if rows:
            cols = [desc[0] for desc in rows.description]
            return [dict(zip(cols, row)) for row in rows]
        return []

    # ----------------------------------------------------------------
    # TRAINING SESSIONS
    # ----------------------------------------------------------------

    async def save_training_session(self, summary: Dict):
        """Save a training session summary."""
        per_pair = summary.get("per_pair", {})
        agent_stats = summary.get("agents", {})
        await self._db.execute(
            """INSERT OR REPLACE INTO training_sessions
               (session_id, started_at, finished_at, strategy, total_trades,
                winning_trades, losing_trades, overall_win_rate, total_pnl,
                best_agent, worst_agent, largest_win, largest_loss,
                per_pair, agent_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                summary.get("session_id", datetime.now().strftime("%Y%m%d_%H%M%S")),
                summary.get("started_at", ""), summary.get("finished_at", datetime.now().isoformat()),
                summary.get("strategy", "Golden Cross EMA-50/200"),
                summary.get("total_trades", 0), summary.get("winning_trades", 0),
                summary.get("losing_trades", 0), summary.get("overall_win_rate", 0),
                summary.get("total_pnl", 0), summary.get("best_agent", ""),
                summary.get("worst_agent", ""),
                summary.get("largest_win", 0), summary.get("largest_loss", 0),
                json.dumps(per_pair), json.dumps(agent_stats),
            ),
        )
        await self._db.commit()

    async def get_training_sessions(self, limit: int = 20) -> List[Dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM training_sessions ORDER BY finished_at DESC LIMIT ?", (limit,)
        )
        if rows:
            cols = [desc[0] for desc in rows.description]
            results = []
            for row in rows:
                d = dict(zip(cols, row))
                d["per_pair"] = json.loads(d.get("per_pair", "{}"))
                d["agent_stats"] = json.loads(d.get("agent_stats", "{}"))
                results.append(d)
            return results
        return []

    # ----------------------------------------------------------------
    # AUDIT LOG
    # ----------------------------------------------------------------

    async def log_audit(self, event_type: str, action: str, agent_id: str = "", details: Dict = None):
        """Append an audit event."""
        await self._db.execute(
            """INSERT INTO audit_log (event_type, agent_id, action, details, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, agent_id, action, json.dumps(details or {}), datetime.now().isoformat()),
        )
        await self._db.commit()

    async def get_audit_log(self, event_type: Optional[str] = None, since: Optional[str] = None, limit: int = 100) -> List[Dict]:
        clauses = []
        params = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        where = " AND ".join(clauses) if clauses else "1=1"
        params.append(limit)
        rows = await self._db.execute_fetchall(
            f"SELECT * FROM audit_log WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        if rows:
            cols = [desc[0] for desc in rows.description]
            results = []
            for row in rows:
                d = dict(zip(cols, row))
                d["details"] = json.loads(d.get("details", "{}"))
                results.append(d)
            return results
        return []

    # ----------------------------------------------------------------
    # UTILITY
    # ----------------------------------------------------------------

    async def vacuum(self):
        """Compact the database file."""
        await self._db.execute("VACUUM")
        logger.info("[DB] VACUUM complete")

    async def get_table_counts(self) -> Dict[str, int]:
        """Quick row counts for all tables — useful for health checks."""
        tables = [
            "trades", "agents", "portfolios", "treasury",
            "treasury_settings", "ohlcv_cache", "training_sessions",
            "wallet", "audit_log",
        ]
        counts = {}
        for t in tables:
            row = await self._db.execute_fetchall(f"SELECT COUNT(*) FROM {t}")
            counts[t] = row[0][0] if row else 0
        return counts