import os
import json
import time

LEDGER_PATH = "C:/Users/danie/program/LUMAX/.logs/trading_ledger.json"

class LumaxBookkeeper:
    def __init__(self, initial_capital=10.0):
        self.ledger_path = LEDGER_PATH
        self.initial_capital = initial_capital
        self.load_or_init_ledger()

    def load_or_init_ledger(self):
        """Initializes or reads the persistent netbooking sheet."""
        if not os.path.exists(self.ledger_path):
            schema = {
                "meta": { "initialized_at": time.strftime("%Y-%m-%d %H:%M:%S"), "currency": "USDT" },
                "account_balances": { "base_capital": self.initial_capital, "current_pool": self.initial_capital, "depin_accrued": 0.0 },
                "daily_risk_metrics": { "daily_loss_limit": 2.0, "current_daily_loss": 0.0, "last_reset_date": time.strftime("%Y-%m-%d") },
                "trade_history": []
            }
            with open(self.ledger_path, 'w') as f:
                json.dump(schema, f, indent=2)
        
        with open(self.ledger_path, 'r') as f:
            self.data = json.load(f)

    def enforce_safety_guardrails(self, suggested_bet_amount):
        """
        THE ANTI-DRAIN ESCAPE MATRIX:
        Evaluates risk parameters before allowing any agent to touch capital.
        """
        # 1. Reset daily loss limits if a new day has dawned
        current_date = time.strftime("%Y-%m-%d")
        if self.data["daily_risk_metrics"]["last_reset_date"] != current_date:
            self.data["daily_risk_metrics"]["current_daily_loss"] = 0.0
            self.data["daily_risk_metrics"]["last_reset_date"] = current_date
            self.save_ledger()

        metrics = self.data["daily_risk_metrics"]
        balances = self.data["account_balances"]

        # 2. Check if daily loss cap is already breached
        if metrics["current_daily_loss"] >= metrics["daily_loss_limit"]:
            print("🚨 [BOOKKEEPER STOP] Daily loss limit breached ($2.00)! Freezing all trading threads.")
            return {"allowed": False, "reason": "DAILY_LOSS_LIMIT_EXCEEDED", "allocated_size": 0.0}

        # 3. Dynamic Position Sizing based on account scale ($0-$20 -> max 25% sizing)
        current_pool = balances["current_pool"]
        max_allowed_position = current_pool * 0.25 # 25% safe sizing lock
        
        if suggested_bet_amount > max_allowed_position:
            allocated = max_allowed_position
        else:
            allocated = suggested_bet_amount

        # 4. Strict absolute floor protection: Never let account drain below $5.00 baseline
        if (current_pool - allocated) < 5.00:
            print("🚨 [BOOKKEEPER STOP] Transaction would violate absolute $5.00 equity floor bounds!")
            return {"allowed": False, "reason": "EQUITY_FLOOR_VIOLATION", "allocated_size": 0.0}

        return {"allowed": True, "reason": "PROCEED_SAFE", "allocated_size": round(allocated, 4)}

    def record_transaction(self, trade_type, pair, execution_price, size, realized_pnl=0.0):
        """Logs trade execution and alters balance tables dynamically."""
        self.data["account_balances"]["current_pool"] += realized_pnl
        if realized_pnl < 0:
            self.data["daily_risk_metrics"]["current_daily_loss"] += abs(realized_pnl)

        trade_log = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": trade_type, # BUY / SELL
            "pair": pair,
            "price": execution_price,
            "size": size,
            "pnl": realized_pnl
        }
        self.data["trade_history"].append(trade_log)
        self.save_ledger()
        print(f"📝 [NETBOOKING] Logged {trade_type} for {pair}. Pool adjusted to: ${self.data['account_balances']['current_pool']:.4f}")

    def inject_depin_yield(self, amount):
        """Safely adds free background network sharing yields directly into your asset pool."""
        self.data["account_balances"]["depin_accrued"] += amount
        self.data["account_balances"]["current_pool"] += amount
        self.save_ledger()
        print(f"🌸 [DEPIN INFLOW] Injected ${amount:.4f} of passive background yield into trading pool.")

    def save_ledger(self):
        with open(self.ledger_path, 'w') as f:
            json.dump(self.data, f, indent=2)

# Quick local instantiation check
if __name__ == "__main__":
    bk = LumaxBookkeeper(initial_capital=10.0)
    # Test checking a suggested $3.00 bet size on our $10 account
    verdict = bk.enforce_safety_guardrails(3.00)
    print(f"📋 Check Verdict: Allowed={verdict['allowed']} | Allocated Size=${verdict['allocated_size']}")
