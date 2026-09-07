"""
FoveAI Monetizing Treasury Manager
==================================
Handles yield accumulation, reinvestment, sectioning (allocation),
safeguarding reserve caps, automated reinvestments, and payouts.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from coinex_integration import CoinExV2Client, CoinExConfig
from security import SecureStorage, RiskManager, AuditLogger

logger = logging.getLogger("treasury_manager")


class TreasuryManager:
    """Manages secure yield accumulation, sectioning, safeguarding, and automated reinvestments."""

    def __init__(self, config_dir: Path = Path("Data/monetizing"), db=None):
        self.config_dir = config_dir
        self.storage_dir = config_dir / "storage"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db = db  # MonetizingDB instance (injected)
        
        self.settings_file = self.storage_dir / "treasury_settings.json"
        self.state_file = self.storage_dir / "treasury_state.json"
        
        # Default allocation percentages (Sectioning)
        self.grinding_swarm_pct = 0.40   # 40% re-invested into CET Grinding Swarm
        self.safeguard_reserve_pct = 0.30 # 30% locked in stablecoins (never traded)
        self.dispense_payout_pct = 0.30   # 30% accumulated for core team payout
        
        # Thresholds
        self.min_reinvest_amount_usd = 2.0  # Minimum USDT to trigger auto-invest buy
        self.min_dispense_amount_usd = 10.0 # Minimum accumulated to trigger payout dispensing
        
        # Accumulated balances tracker (USD value equivalents)
        self.accumulated_grinding = 0.0
        self.accumulated_reserve = 0.0
        self.accumulated_dispense = 0.0
        self.total_yield_accumulated = 0.0
        
        # Payout destination
        self.payout_address = ""
        self.payout_network = "SOL"
        
        self.load_settings()
        self.load_state()

    def load_settings(self):
        """Load treasury settings from disk."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file) as f:
                    data = json.load(f)
                    self.grinding_swarm_pct = data.get("grinding_swarm_pct", self.grinding_swarm_pct)
                    self.safeguard_reserve_pct = data.get("safeguard_reserve_pct", self.safeguard_reserve_pct)
                    self.dispense_payout_pct = data.get("dispense_payout_pct", self.dispense_payout_pct)
                    self.min_reinvest_amount_usd = data.get("min_reinvest_amount_usd", self.min_reinvest_amount_usd)
                    self.min_dispense_amount_usd = data.get("min_dispense_amount_usd", self.min_dispense_amount_usd)
                    self.payout_address = data.get("payout_address", self.payout_address)
                    self.payout_network = data.get("payout_network", self.payout_network)
                logger.info("[TreasuryManager] Settings loaded successfully.")
            except Exception as e:
                logger.error(f"[TreasuryManager] Error loading settings: {e}")

    def save_settings(self):
        """Save treasury settings to disk."""
        data = {
            "grinding_swarm_pct": self.grinding_swarm_pct,
            "safeguard_reserve_pct": self.safeguard_reserve_pct,
            "dispense_payout_pct": self.dispense_payout_pct,
            "min_reinvest_amount_usd": self.min_reinvest_amount_usd,
            "min_dispense_amount_usd": self.min_dispense_amount_usd,
            "payout_address": self.payout_address,
            "payout_network": self.payout_network
        }
        try:
            with open(self.settings_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("[TreasuryManager] Settings saved.")
        except Exception as e:
            logger.error(f"[TreasuryManager] Error saving settings: {e}")

    def load_state(self):
        """Load treasury state balances from JSON (DB loading is async — call load_state_from_db separately)."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self.accumulated_grinding = data.get("accumulated_grinding", 0.0)
                    self.accumulated_reserve = data.get("accumulated_reserve", 0.0)
                    self.accumulated_dispense = data.get("accumulated_dispense", 0.0)
                    self.total_yield_accumulated = data.get("total_yield_accumulated", 0.0)
                logger.info("[TreasuryManager] State loaded successfully.")
            except Exception as e:
                logger.error(f"[TreasuryManager] Error loading state: {e}")

    async def load_state_from_db(self):
        """Load treasury state from DB (overrides JSON if available)."""
        if not self.db:
            return
        try:
            data = await self.db.get_treasury()
            if data:
                self.accumulated_grinding = data.get("accumulated_grinding", self.accumulated_grinding)
                self.accumulated_reserve = data.get("accumulated_reserve", self.accumulated_reserve)
                self.accumulated_dispense = data.get("accumulated_dispense", self.accumulated_dispense)
                self.total_yield_accumulated = data.get("total_yield_accumulated", self.total_yield_accumulated)
                logger.info("[TreasuryManager] State loaded from database.")
        except Exception as e:
            logger.warning(f"[TreasuryManager] DB load failed, using JSON fallback: {e}")

    async def save_state(self):
        """Save treasury state balances to DB (preferred) or JSON (fallback)."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "accumulated_grinding": self.accumulated_grinding,
            "accumulated_reserve": self.accumulated_reserve,
            "accumulated_dispense": self.accumulated_dispense,
            "total_yield_accumulated": self.total_yield_accumulated
        }
        # Try DB first
        if self.db:
            try:
                await self.db.update_treasury(
                    grinding=self.accumulated_grinding,
                    reserve=self.accumulated_reserve,
                    dispense=self.accumulated_dispense,
                    total_yield=self.total_yield_accumulated,
                )
                logger.debug("[TreasuryManager] State saved to database.")
                return
            except Exception as e:
                logger.warning(f"[TreasuryManager] DB save failed, falling back to JSON: {e}")
        # Fallback: JSON
        try:
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[TreasuryManager] Error saving state: {e}")

    async def process_incoming_yield(self, amount_usd: float, source: str) -> Dict[str, float]:
        """Accumulation & Sectioning: Divide incoming yield into designated pots."""
        if amount_usd <= 0:
            return {}

        grinding_share = amount_usd * self.grinding_swarm_pct
        reserve_share = amount_usd * self.safeguard_reserve_pct
        dispense_share = amount_usd * self.dispense_payout_pct

        self.accumulated_grinding += grinding_share
        self.accumulated_reserve += reserve_share
        self.accumulated_dispense += dispense_share
        self.total_yield_accumulated += amount_usd

        await self.save_state()

        # Log event in audit
        try:
            audit = AuditLogger(self.config_dir / "logs")
            audit.log_event(
                event_type="treasury",
                user_id="treasury_manager",
                action="ACCUMULATE_YIELD",
                details={
                    "source": source,
                    "total_usd": amount_usd,
                    "shares": {
                        "grinding": grinding_share,
                        "reserve": reserve_share,
                        "dispense": dispense_share
                    }
                }
            )
        except Exception as e:
            logger.warning(f"[TreasuryManager] Could not log audit: {e}")

        logger.info(f"[TreasuryManager] Accumulated ${amount_usd:.4f} USD from {source}. "
                    f"Grinding: +${grinding_share:.4f} | Reserve: +${reserve_share:.4f} | Dispense: +${dispense_share:.4f}")

        return {
            "grinding": grinding_share,
            "reserve": reserve_share,
            "dispense": dispense_share
        }

    async def auto_invest_accumulated_yield(self, client: CoinExV2Client) -> Optional[Dict[str, Any]]:
        """Automating & Reinvestment: Re-invest the accumulated grinding budget to buy CET on CoinEx."""
        if self.accumulated_grinding < self.min_reinvest_amount_usd:
            logger.info(f"[TreasuryManager] Grinding yield (${self.accumulated_grinding:.2f}) "
                        f"below minimum reinvest threshold (${self.min_reinvest_amount_usd:.2f})")
            return None

        # Safeguarding check: fetch balances
        try:
            balance = await client.get_balance()
            usdt_avail = balance.available.get("USDT", 0.0)
            
            # Never spend more than is actually available in spot USDT
            invest_amount_usd = min(self.accumulated_grinding, usdt_avail)
            
            # Verify market constraints
            market_info = await client.get_market_info("CETUSDT")
            min_amount = float(market_info.get("min_amount", 999999))
            ticker_price = await client.get_market_price("CETUSDT")
            
            if ticker_price <= 0:
                logger.error("[TreasuryManager] Invalid CET market price.")
                return None
                
            cet_amount = invest_amount_usd / ticker_price
            
            if cet_amount >= min_amount:
                logger.info(f"[TreasuryManager] Re-investing ${invest_amount_usd:.2f} USDT into CET...")
                order_result = await client.place_order(
                    market="CETUSDT",
                    side="buy",
                    amount=invest_amount_usd,
                    order_type="market"
                )
                
                # Deduct reinvested balance
                self.accumulated_grinding -= invest_amount_usd
                await self.save_state()
                
                # Log audit
                try:
                    audit = AuditLogger(self.config_dir / "logs")
                    audit.log_event(
                        event_type="treasury",
                        user_id="treasury_manager",
                        action="REINVEST_YIELD_CET",
                        details={
                            "invest_usd": invest_amount_usd,
                            "cet_purchased": cet_amount,
                            "price": ticker_price,
                            "order_result": order_result
                        }
                    )
                except Exception as audit_err:
                    logger.warning(f"Could not log audit: {audit_err}")
                
                return {
                    "status": "reinvested",
                    "invested_usd": invest_amount_usd,
                    "cet_purchased": cet_amount,
                    "price": ticker_price
                }
            else:
                logger.warning(f"[TreasuryManager] Target CET purchase amount ({cet_amount:.2f}) "
                               f"is below CoinEx minimum {min_amount}")
        except Exception as e:
            logger.error(f"[TreasuryManager] Reinvestment execution error: {e}")
            
        return None

    async def dispense_payouts(self, client: CoinExV2Client) -> Optional[Dict[str, Any]]:
        """Dispensing & Safeguarding: Automatically dispense core payouts if thresholds are met and target is configured."""
        if not self.payout_address:
            logger.info("[TreasuryManager] Dispensing skipped - No payout_address configured.")
            return None
            
        if self.accumulated_dispense < self.min_dispense_amount_usd:
            logger.info(f"[TreasuryManager] Dispense balance (${self.accumulated_dispense:.2f}) "
                        f"below minimum payout threshold (${self.min_dispense_amount_usd:.2f})")
            return None

        try:
            # Check CoinEx balances to ensure we have the funds to dispense
            balance = await client.get_balance()
            
            # We default to dispensing SOL or USDT on the designated network
            coin_to_withdraw = "USDT" if self.payout_network != "SOL" else "SOL"
            avail_amount = balance.available.get(coin_to_withdraw, 0.0)
            
            # Determine equivalent value to withdraw
            coin_price = 1.0 if coin_to_withdraw == "USDT" else await client.get_market_price("SOLUSDT")
            if coin_price <= 0:
                logger.error("[TreasuryManager] Invalid coin price for dispensing.")
                return None
                
            withdraw_amount = self.accumulated_dispense / coin_price
            
            # Safeguard: Ensure we don't withdraw more than is available in exchange
            if withdraw_amount > avail_amount:
                logger.warning(f"[TreasuryManager] Exchange available balance of {coin_to_withdraw} ({avail_amount:.4f}) "
                               f"is lower than requested dispense amount ({withdraw_amount:.4f}). Capping withdrawal.")
                withdraw_amount = avail_amount
                
            if withdraw_amount <= 0:
                logger.error("[TreasuryManager] Dispensing amount is zero.")
                return None

            # Execute withdrawal call
            logger.info(f"[TreasuryManager] Dispensing {withdraw_amount:.4f} {coin_to_withdraw} to {self.payout_address}...")
            result = await client.withdraw(
                coin=coin_to_withdraw,
                address=self.payout_address,
                amount=withdraw_amount,
                network=self.payout_network
            )
            
            # Deduct payout pot
            deducted_usd = withdraw_amount * coin_price
            self.accumulated_dispense -= deducted_usd
            await self.save_state()
            
            # Log audit
            try:
                audit = AuditLogger(self.config_dir / "logs")
                audit.log_event(
                    event_type="treasury",
                    user_id="treasury_manager",
                    action="DISPENSE_PAYOUT",
                    details={
                        "coin": coin_to_withdraw,
                        "amount": withdraw_amount,
                        "usd_value": deducted_usd,
                        "address": self.payout_address,
                        "result": result
                    }
                )
            except Exception as audit_err:
                logger.warning(f"Could not log audit: {audit_err}")
                
            return {
                "status": "dispensed",
                "coin": coin_to_withdraw,
                "amount": withdraw_amount,
                "usd_value": deducted_usd,
                "address": self.payout_address
            }
        except Exception as e:
            logger.error(f"[TreasuryManager] Dispensing payout error: {e}")
            
        return None

    def get_treasury_status(self) -> Dict[str, Any]:
        """Retrieve complete status of allocations and limits."""
        return {
            "grinding_share_pct": self.grinding_swarm_pct,
            "reserve_share_pct": self.safeguard_reserve_pct,
            "dispense_share_pct": self.dispense_payout_pct,
            "balances": {
                "grinding_usd": self.accumulated_grinding,
                "reserve_usd": self.accumulated_reserve,
                "dispense_usd": self.accumulated_dispense,
                "total_yield_usd": self.total_yield_accumulated
            },
            "payout": {
                "address": self.payout_address or "Not configured",
                "network": self.payout_network,
                "min_dispense_threshold": self.min_dispense_amount_usd
            },
            "reinvest": {
                "min_reinvest_threshold": self.min_reinvest_amount_usd
            }
        }
