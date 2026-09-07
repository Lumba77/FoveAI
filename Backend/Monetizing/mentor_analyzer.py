"""
LLM Mentor Analyzer - Cloud-based trading review
Uses Ollama Cloud (qwen3.5:32b-cloud) for periodic strategy analysis
"""

import httpx
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Ollama Cloud Configuration
OLLAMA_CLOUD_URL = "https://ollama.com/v1/chat/completions"
OLLAMA_CLOUD_KEY = "a87e5fe6d3334214b866ba8c79af3460.lCOisLzsLJ8X9Mug6VIfwQfU"
MENTOR_MODEL = "qwen3.5:32b-cloud"  # Balanced 32B model for analysis


def format_trades(trade_history: List[Dict]) -> str:
    """Format trade history for LLM consumption."""
    if not trade_history:
        return "No trades yet."
    
    lines = []
    for i, trade in enumerate(trade_history[-15:], 1):  # Last 15 trades max
        lines.append(
            f"{i}. {trade.get('type', 'UNKNOWN')} | "
            f"Amount: {trade.get('amount', 0):.4f} | "
            f"Price: ${trade.get('price', 0):.6f} | "
            f"Result: {trade.get('result', 'N/A')} | "
            f"Profit: ${trade.get('profit', 0):.4f}"
        )
    return "\n".join(lines)


async def analyze_trades(
    trade_history: List[Dict],
    current_holdings: Dict[str, float],
    indicators: Dict[str, float]
) -> Dict:
    """Send trade history to cloud LLM for analysis."""
    
    holdings_text = (
        f"- CET: {current_holdings.get('cet', 0):.2f}\n"
        f"- USDT: {current_holdings.get('usdt', 0):.2f}"
    )
    
    indicators_text = (
        f"- MA9: {indicators.get('ma9', 0):.6f}\n"
        f"- MA26: {indicators.get('ma26', 0):.6f}\n"
        f"- RSI: {indicators.get('rsi', 0):.1f}\n"
        f"- MACD: {indicators.get('macd', 0):.6f}"
    )
    
    prompt = f"""You are a trading mentor analyzing CET/USDT micro-trading performance.

CURRENT HOLDINGS:
{holdings_text}

RECENT TRADES (last 15):
{format_trades(trade_history)}

TECHNICAL INDICATORS:
{indicators_text}

TASK:
1. Analyze win/loss pattern - is the strategy working?
2. Identify any mistakes (chasing pumps, selling too early, bad entry timing)
3. Suggest parameter adjustments (position size %, RSI thresholds, MA periods)
4. Rate overall strategy health (0-100%)
5. Provide a confidence modifier (0.0-1.0) for next trades

Respond in valid JSON only:
{{
  "win_rate": 0.XX,
  "total_trades_analyzed": X,
  "mistakes": ["mistake1", "mistake2"],
  "suggestions": ["suggestion1", "suggestion2"],
  "health_score": XX,
  "confidence_modifier": 0.XX,
  "action": "CONTINUE" | "REDUCE_SIZE" | "PAUSE",
  "reasoning": "brief explanation"
}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OLLAMA_CLOUD_URL,
                headers={"Authorization": f"Bearer {OLLAMA_CLOUD_KEY}"},
                json={
                    "model": MENTOR_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,  # Low temp for consistent analysis
                    "max_tokens": 600,
                    "stream": False
                }
            )
            
            if resp.status_code == 200:
                response_data = resp.json()
                content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Parse JSON from response
                try:
                    # Try to extract JSON from the response
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0]
                    elif "{" in content:
                        content = content[content.find("{"):content.rfind("}")+1]
                    
                    result = json.loads(content.strip())
                    logger.info(f"🧠 MENTOR ANALYSIS COMPLETE: Health={result.get('health_score', 'N/A')}%, Action={result.get('action', 'N/A')}")
                    return result
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse mentor JSON: {e}")
                    return get_default_analysis()
            else:
                logger.warning(f"Ollama Cloud returned {resp.status_code}")
                return get_default_analysis()
                
    except httpx.RequestError as e:
        logger.warning(f"Could not reach Ollama Cloud: {e}")
        return get_default_analysis()
    except Exception as e:
        logger.warning(f"Mentor analysis failed: {e}")
        return get_default_analysis()


def get_default_analysis() -> Dict:
    """Return safe defaults when LLM is unavailable."""
    return {
        "win_rate": 0.5,
        "total_trades_analyzed": 0,
        "mistakes": [],
        "suggestions": ["Continue monitoring performance"],
        "health_score": 75,
        "confidence_modifier": 0.8,
        "action": "CONTINUE",
        "reasoning": "Using default analysis - LLM unavailable"
    }


async def quick_confidence_check(indicators: Dict[str, float], recent_pnl: float) -> float:
    """
    Quick confidence check (0.0-1.0) for real-time adjustment.
    Lighter than full analysis - uses smaller prompt.
    """
    
    prompt = f"""Quick trading confidence check.

INDICATORS:
- RSI: {indicators.get('rsi', 50):.1f} (35=oversold, 65=overbought)
- MACD: {indicators.get('macd', 0):.6f} (positive=bullish)
- Recent PnL: ${recent_pnl:.4f}

Return ONLY a number 0.0-1.0 representing confidence in next trade success."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                OLLAMA_CLOUD_URL,
                headers={"Authorization": f"Bearer {OLLAMA_CLOUD_KEY}"},
                json={
                    "model": MENTOR_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 10,
                    "stream": False
                }
            )
            
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "0.8")
                # Extract number from response
                try:
                    confidence = float(content.strip().replace("Confidence: ", ""))
                    return max(0.0, min(1.0, confidence))
                except ValueError:
                    return 0.8
    except Exception:
        pass
    
    return 0.8  # Default confidence


class MentorMemory:
    """Stores mentor analysis history for trend tracking."""
    
    def __init__(self, storage_path: str = "Data/monetizing/mentor_memory.json"):
        self.storage_path = storage_path
        self.analyses: List[Dict] = []
        self._load()
    
    def add_analysis(self, analysis: Dict):
        """Add a new analysis to memory."""
        analysis["timestamp"] = datetime.now().isoformat()
        self.analyses.append(analysis)
        if len(self.analyses) > 100:  # Keep last 100 analyses
            self.analyses = self.analyses[-100:]
        self._save()
    
    def get_trend(self) -> str:
        """Analyze if mentor scores are improving or declining."""
        if len(self.analyses) < 3:
            return "INSUFFICIENT_DATA"
        
        recent = [a.get("health_score", 75) for a in self.analyses[-5:]]
        older = [a.get("health_score", 75) for a in self.analyses[-10:-5]]
        
        if not older:
            return "STABLE"
        
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        
        if avg_recent > avg_older + 5:
            return "IMPROVING"
        elif avg_recent < avg_older - 5:
            return "DECLINING"
        return "STABLE"
    
    def _load(self):
        """Load memory from disk."""
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                self.analyses = data.get("analyses", [])
        except FileNotFoundError:
            self.analyses = []
        except Exception as e:
            logger.warning(f"Failed to load mentor memory: {e}")
            self.analyses = []
    
    def _save(self):
        """Save memory to disk."""
        try:
            with open(self.storage_path, "w") as f:
                json.dump({"analyses": self.analyses}, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save mentor memory: {e}")


# Singleton instance for easy import
_mentor_memory = None

def get_mentor_memory() -> MentorMemory:
    """Get or create mentor memory singleton."""
    global _mentor_memory
    if _mentor_memory is None:
        _mentor_memory = MentorMemory()
    return _mentor_memory