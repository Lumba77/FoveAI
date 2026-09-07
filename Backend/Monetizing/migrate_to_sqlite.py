"""
FoveAI Monetizing — JSON to SQLite Migration
=============================================
One-shot script to migrate existing JSON state files into the new SQLite DB.

Reads:
  - Data/monetizing/swarm_state.json       → agents + wallet tables
  - Data/monetizing/storage/treasury_state.json  → treasury table
  - Data/monetizing/storage/treasury_settings.json → treasury_settings table
  - Data/monetizing/paper_trading/trades.json     → trades table
  - Data/monetizing/paper_trading/portfolios.json  → portfolios table
  - Data/monetizing/paper_trading/training_log.json → training_sessions table

Creates:
  - Data/monetizing/monetizing.db

Usage:
    cd backend/Monetizing
    python migrate_to_sqlite.py          # dry run (no writes)
    python migrate_to_sqlite.py --apply  # actually write to DB
"""

import asyncio
import json
import sys
from pathlib import Path

# Add current dir to path for direct import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from monetizing_db import MonetizingDB

DATA_DIR = Path("../../Data/monetizing")
PAPER_DIR = DATA_DIR / "paper_trading"
STORAGE_DIR = DATA_DIR / "storage"


def load_json(path: Path) -> dict:
    """Load a JSON file, return empty dict if missing."""
    if not path.exists():
        print(f"  [SKIP] {path} — not found")
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        print(f"  [OK]   {path} — loaded")
        return data
    except Exception as e:
        print(f"  [ERR]  {path} — {e}")
        return {}


async def migrate(apply: bool = False):
    db_path = str(DATA_DIR / "monetizing.db")
    print(f"\n{'='*60}")
    print(f"  FoveAI Monetizing: JSON → SQLite Migration")
    print(f"  Mode: {'APPLY (will write DB)' if apply else 'DRY RUN (read-only)'}")
    print(f"  DB:   {db_path}")
    print(f"{'='*60}\n")

    # --- Load source data ---
    print("1. Loading JSON files...\n")

    swarm_state = load_json(DATA_DIR / "swarm_state.json")
    treasury_state = load_json(STORAGE_DIR / "treasury_state.json")
    treasury_settings = load_json(STORAGE_DIR / "treasury_settings.json")
    trades_data = load_json(PAPER_DIR / "trades.json")
    portfolios_data = load_json(PAPER_DIR / "portfolios.json")
    training_data = load_json(PAPER_DIR / "training_log.json")

    if not any([swarm_state, treasury_state, trades_data, portfolios_data]):
        print("\n  No source data found. Nothing to migrate.")
        return

    # --- Initialize DB ---
    print(f"\n2. Initializing database...\n")

    if not apply:
        print("  [DRY RUN] Would create/verify tables at:", db_path)

    db = await MonetizingDB.create(db_path)

    # --- Migrate agents ---
    agents_data = swarm_state.get("agents", {})
    if agents_data:
        print(f"\n3. Migrating {len(agents_data)} agents...\n")
        for aid, a_data in agents_data.items():
            agent = {
                "agent_id": aid,
                "name": a_data.get("name", "Unknown"),
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
            }
            print(f"  Agent: {aid} ({agent['name']}) — status={agent['status']}")
            if apply:
                await db.upsert_agent(agent)
    else:
        print("\n3. No agents to migrate.")

    # --- Migrate wallet ---
    if swarm_state.get("total_earnings") is not None:
        print(f"\n4. Migrating wallet state...\n")
        print(f"  total_earnings: {swarm_state.get('total_earnings', 0)}")
        print(f"  solana_address: {swarm_state.get('solana_address', 'N/A')}")
        if apply:
            await db.update_wallet(
                total_earnings=swarm_state.get("total_earnings", 0),
                solana_address=swarm_state.get("solana_address", ""),
                sol_balance=swarm_state.get("actual_sol_balance", 0),
            )
    else:
        print("\n4. No wallet data to migrate.")

    # --- Migrate treasury ---
    if treasury_state:
        print(f"\n5. Migrating treasury state...\n")
        print(f"  grinding:   ${treasury_state.get('accumulated_grinding', 0):.2f}")
        print(f"  reserve:    ${treasury_state.get('accumulated_reserve', 0):.2f}")
        print(f"  dispense:   ${treasury_state.get('accumulated_dispense', 0):.2f}")
        print(f"  total_yield: ${treasury_state.get('total_yield_accumulated', 0):.2f}")
        if apply:
            await db.update_treasury(
                grinding=treasury_state.get("accumulated_grinding", 0),
                reserve=treasury_state.get("accumulated_reserve", 0),
                dispense=treasury_state.get("accumulated_dispense", 0),
                total_yield=treasury_state.get("total_yield_accumulated", 0),
            )
    else:
        print("\n5. No treasury state to migrate.")

    # --- Migrate treasury settings ---
    if treasury_settings:
        print(f"\n6. Migrating treasury settings...\n")
        if apply:
            await db.update_treasury_settings(treasury_settings)
            print("  Settings migrated.")
    else:
        print("\n6. No treasury settings to migrate.")

    # --- Migrate trades ---
    trades_list = trades_data.get("trades", [])
    if trades_list:
        print(f"\n7. Migrating {len(trades_list)} trades...\n")
        count = 0
        for t in trades_list:
            trade = {
                "trade_id": t.get("trade_id", f"migrated_{count}"),
                "agent_id": t.get("agent_id", "unknown"),
                "pair": t.get("pair", ""),
                "side": t.get("side", "buy"),
                "order_type": t.get("order_type", "market"),
                "amount": float(t.get("amount", 0)),
                "price": float(t.get("price", 0)),
                "usdt_value": float(t.get("usdt_value", 0)),
                "profit_usdt": float(t.get("profit_usdt", 0)),
                "profit_pct": float(t.get("profit_pct", 0)),
                "reason": t.get("reason", ""),
                "paper": t.get("paper", True),
                "mentor_reviewed": t.get("mentor_reviewed", False),
                "timestamp": t.get("timestamp", ""),
            }
            if apply:
                await db.insert_trade(trade)
            count += 1
        print(f"  Migrated {count} trades")
    else:
        print("\n7. No trades to migrate.")

    # --- Migrate portfolios ---
    portfolios = portfolios_data.get("portfolios", {})
    if portfolios:
        print(f"\n8. Migrating {len(portfolios)} portfolios...\n")
        for aid, pd in portfolios.items():
            portfolio = {
                "agent_id": pd.get("agent_id", aid),
                "usdt_balance": float(pd.get("usdt_balance", 0)),
                "holdings": pd.get("holdings", {}),
                "starting_usdt": float(pd.get("starting_usdt", 20)),
                "total_pnl": float(pd.get("total_pnl", 0)),
                "win_count": int(pd.get("win_count", 0)),
                "loss_count": int(pd.get("loss_count", 0)),
            }
            if apply:
                await db.upsert_portfolio(portfolio)
            print(f"  Portfolio: {aid} — USDT={portfolio['usdt_balance']:.2f} PnL={portfolio['total_pnl']:.4f}")
    else:
        print("\n8. No portfolios to migrate.")

    # --- Migrate training sessions ---
    sessions = training_data.get("sessions", [])
    if sessions:
        print(f"\n9. Migrating {len(sessions)} training sessions...\n")
        for s in sessions:
            if apply:
                await db.save_training_session(s)
            print(f"  Session: {s.get('session_id', 'unknown')}")
    else:
        print("\n9. No training sessions to migrate.")

    # --- Summary ---
    counts = await db.get_table_counts()
    print(f"\n{'='*60}")
    print(f"  MIGRATION {'COMPLETE' if apply else 'DRY RUN COMPLETE'}")
    print(f"{'='*60}")
    print(f"\n  Database row counts:")
    for table, count in counts.items():
        print(f"    {table:25s} {count:>6d} rows")
    print()

    await db.close()

    if apply:
        print("  All JSON data has been migrated to:", db_path)
        print("  You can now update your modules to use MonetizingDB instead of JSON files.")
        print("  Original JSON files are preserved (not deleted).")
    else:
        print("  This was a DRY RUN — no data was written.")
        print("  Run with --apply to actually migrate:")
        print("    python migrate_to_sqlite.py --apply")


if __name__ == "__main__":
    apply_flag = "--apply" in sys.argv
    asyncio.run(migrate(apply=apply_flag))