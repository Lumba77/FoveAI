"""
FoveAI Monetizing Security Module
=================================
Secure handling of API keys, risk management, and audit logging.
"""

import json
import hashlib
import base64
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Custom exception for security errors."""
    pass


@dataclass
class AuditEvent:
    """Audit log event."""
    timestamp: str
    event_type: str
    user_id: str
    action: str
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = "127.0.0.1"
    user_agent: str = "FoveAI-Monetizing"


@dataclass 
class APIKeyStore:
    """Secure storage for API keys."""
    provider: str
    key_id: str
    api_key_encrypted: str
    created_at: str
    last_used: Optional[str] = None
    enabled: bool = True


class SecureStorage:
    """Secure key storage using OS-level encryption where available."""
    
    def __init__(self, storage_dir: Path = Path("Data/monetizing/storage")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.keys: Dict[str, APIKeyStore] = {}
        self._load_keys()
    
    def _load_keys(self):
        """Load keys from storage."""
        storage_file = self.storage_dir / "keys.json"
        if storage_file.exists():
            try:
                with open(storage_file) as f:
                    data = json.load(f)
                    for key_id, key_data in data.items():
                        self.keys[key_id] = APIKeyStore(
                            provider=key_data.get("provider", ""),
                            key_id=key_data.get("key_id", ""),
                            api_key_encrypted=key_data.get("api_key_encrypted", ""),
                            created_at=key_data.get("created_at", ""),
                            last_used=key_data.get("last_used"),
                            enabled=key_data.get("enabled", True)
                        )
            except Exception as e:
                logger.error(f"[SecureStorage] Error loading keys: {e}")
    
    def _save_keys(self):
        """Save keys to storage."""
        storage_file = self.storage_dir / "keys.json"
        data = {}
        for key_id, key_store in self.keys.items():
            data[key_id] = {
                "provider": key_store.provider,
                "key_id": key_store.key_id,
                "api_key_encrypted": key_store.api_key_encrypted,
                "created_at": key_store.created_at,
                "last_used": key_store.last_used,
                "enabled": key_store.enabled
            }
        with open(storage_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def store_api_key(self, provider: str, key_id: str, api_key: str) -> APIKeyStore:
        """Store an API key (encrypted)."""
        # Simple obfuscation - in production, use proper encryption
        encrypted = base64.b64encode(api_key.encode()).decode()
        
        key_store = APIKeyStore(
            provider=provider,
            key_id=key_id,
            api_key_encrypted=encrypted,
            created_at=datetime.now().isoformat()
        )
        
        self.keys[key_id] = key_store
        self._save_keys()
        
        logger.info(f"[SecureStorage] Stored API key for {provider}: {key_id}")
        return key_store
    
    def get_api_key(self, key_id: str) -> Optional[str]:
        """Retrieve an API key (decrypted)."""
        key_store = self.keys.get(key_id)
        if not key_store:
            return None
        
        # Simple obfuscation - in production, use proper encryption
        try:
            api_key = base64.b64decode(key_store.api_key_encrypted).decode()
            key_store.last_used = datetime.now().isoformat()
            self._save_keys()
            return api_key
        except Exception as e:
            logger.error(f"[SecureStorage] Error retrieving key {key_id}: {e}")
            return None
    
    def remove_api_key(self, key_id: str) -> bool:
        """Remove an API key."""
        if key_id in self.keys:
            del self.keys[key_id]
            self._save_keys()
            return True
        return False
    
    def list_keys(self) -> List[APIKeyStore]:
        """List all stored keys."""
        return list(self.keys.values())


class RiskManager:
    """Manages risk parameters and enforces limits."""
    
    def __init__(
        self, 
        max_daily_loss_usd: float = 100.0,
        max_position_size_usd: float = 500.0,
        max_trades_per_day: int = 10,
        max_concurrent_positions: int = 3,
        storage_dir: Path = Path("Data/monetizing/storage")
    ):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Defaults
        self.max_daily_loss_usd = max_daily_loss_usd
        self.max_position_size_usd = max_position_size_usd
        self.max_trades_per_day = max_trades_per_day
        self.max_concurrent_positions = max_concurrent_positions
        
        # Daily counters
        self.daily_loss = 0.0
        self.daily_profit = 0.0
        self.trades_today = 0
        self.current_positions = 0
        self.last_reset = datetime.now().date()
        
        self.load_settings()
    
    def save_settings(self):
        """Save risk settings to disk."""
        settings_file = self.storage_dir / "risk_settings.json"
        data = {
            "max_daily_loss_usd": self.max_daily_loss_usd,
            "max_position_size_usd": self.max_position_size_usd,
            "max_trades_per_day": self.max_trades_per_day,
            "max_concurrent_positions": self.max_concurrent_positions
        }
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"[RiskManager] Settings saved: {data}")

    def load_settings(self):
        """Load risk settings from disk."""
        settings_file = self.storage_dir / "risk_settings.json"
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    data = json.load(f)
                    self.max_daily_loss_usd = data.get("max_daily_loss_usd", self.max_daily_loss_usd)
                    self.max_position_size_usd = data.get("max_position_size_usd", self.max_position_size_usd)
                    self.max_trades_per_day = data.get("max_trades_per_day", self.max_trades_per_day)
                    self.max_concurrent_positions = data.get("max_concurrent_positions", self.max_concurrent_positions)
                logger.info(f"[RiskManager] Settings loaded: {data}")
            except Exception as e:
                logger.error(f"[RiskManager] Error loading settings: {e}")

    def _check_reset(self):
        """Reset daily counters if new day."""
        if datetime.now().date() != self.last_reset:
            self.daily_loss = 0.0
            self.daily_profit = 0.0
            self.trades_today = 0
            self.current_positions = 0
            self.last_reset = datetime.now().date()
            logger.info("[RiskManager] Daily counters reset")
    
    def can_open_position(self, estimated_cost: float) -> bool:
        """Check if a new position can be opened."""
        self._check_reset()
        
        if self.current_positions >= self.max_concurrent_positions:
            return False
        
        if estimated_cost > self.max_position_size_usd:
            logger.warning(f"[RiskManager] Position ${estimated_cost:.2f} exceeds max ${self.max_position_size_usd:.2f}")
            return False
        
        return True
    
    def can_trade(self, potential_loss: float) -> bool:
        """Check if trading is within risk limits."""
        self._check_reset()
        
        if self.daily_loss + potential_loss > self.max_daily_loss_usd:
            logger.warning(f"[RiskManager] Potential loss exceeds daily limit")
            return False
        
        if self.trades_today >= self.max_trades_per_day:
            logger.warning(f"[RiskManager] Max trades per day reached")
            return False
        
        return True
    
    def record_trade(self, profit: float, position_size: float):
        """Record a completed trade."""
        self._check_reset()
        
        if profit < 0:
            self.daily_loss += abs(profit)
        else:
            self.daily_profit += profit
        
        self.trades_today += 1
        self.current_positions -= 1  # Position closed
    
    def record_position(self, size: float):
        """Record an open position."""
        self._check_reset()
        self.current_positions += 1
    
    def get_risk_status(self) -> Dict[str, Any]:
        """Get current risk status."""
        self._check_reset()
        
        return {
            "daily_loss": self.daily_loss,
            "daily_profit": self.daily_profit,
            "net_daily": self.daily_profit - self.daily_loss,
            "trades_today": self.trades_today,
            "max_trades_per_day": self.max_trades_per_day,
            "current_positions": self.current_positions,
            "max_concurrent_positions": self.max_concurrent_positions,
            "daily_loss_limit": self.max_daily_loss_usd,
            "position_size_limit": self.max_position_size_usd,
            "trades_remaining": self.max_trades_per_day - self.trades_today,
            "positions_remaining": self.max_concurrent_positions - self.current_positions
        }


class AuditLogger:
    """Audit logging for all monetizing operations."""
    
    def __init__(self, log_dir: Path = Path("Data/monetizing/logs")):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_file = self.log_dir / "audit.log"
    
    def log_event(self, event_type: str, user_id: str, action: str, details: Dict = None):
        """Log an audit event."""
        event = AuditEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            user_id=user_id,
            action=action,
            details=details or {}
        )
        
        # Append to log file
        with open(self.audit_log_file, 'a') as f:
            f.write(json.dumps(asdict(event)) + '\n')
        
        logger.info(f"[Audit] {action} - {event_type} - {user_id}")
    
    def log_trade(
        self, 
        user_id: str, 
        market: str, 
        side: str, 
        price: float, 
        amount: float,
        profit: float = 0.0
    ):
        """Log a trade event."""
        self.log_event(
            event_type="trade",
            user_id=user_id,
            action=f"{side.upper()}_ORDER",
            details={
                "market": market,
                "price": price,
                "amount": amount,
                "profit": profit
            }
        )
    
    def log_api_call(self, user_id: str, api_provider: str, endpoint: str, success: bool):
        """Log an API call."""
        self.log_event(
            event_type="api_call",
            user_id=user_id,
            action=f"{api_provider.upper()}_{endpoint}",
            details={"success": success}
        )
    
    def get_audit_log(self, user_id: str = None, limit: int = 100) -> List[Dict]:
        """Get audit log entries."""
        entries = []
        try:
            with open(self.audit_log_file) as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    entry = json.loads(line.strip())
                    if user_id is None or entry.get("user_id") == user_id:
                        entries.append(entry)
        except FileNotFoundError:
            pass
        return entries


class APIKeyValidator:
    """Validates API key format and requirements."""
    
    VALID_PROVIDERS = {"coinex", "binance", "kraken", "kucoin", "bybit"}
    
    @staticmethod
    def is_valid_api_key(provider: str, key: str) -> bool:
        """Validate API key format."""
        if not key or len(key) < 10:
            return False
        
        # Provider-specific checks
        provider = provider.lower()
        if provider == "coinex":
            # CoinEx keys are typically 32+ hex chars
            try:
                int(key, 16)
                return len(key) >= 32
            except ValueError:
                return False
        
        elif provider == "binance":
            # Binance API keys start with 'b' and are 64 chars
            return len(key) == 64 and key[0] == 'b'
        
        elif provider == "kucoin":
            # KuCoin keys are 36 chars (UUID format)
            import re
            pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
            return bool(re.match(pattern, key))
        
        # Generic check for other providers
        return len(key) >= 20
    
    @staticmethod
    def get_provider_requirements(provider: str) -> Dict[str, Any]:
        """Get API key requirements for a provider."""
        requirements = {
            "coinex": {"min_length": 32, "format": "hexadecimal"},
            "binance": {"min_length": 64, "format": "starts with 'b'"},
            "kraken": {"min_length": 48, "format": "base64"},
            "kucoin": {"min_length": 36, "format": "uuid"},
            "bybit": {"min_length": 36, "format": "alphanumeric"}
        }
        return requirements.get(provider.lower(), {"min_length": 20, "format": "alphanumeric"})