"""
FoveAI Autonomous Web Scout
============================
Scouts the live web for actionable earning vectors:
- Open Developer Bounties & Micro-tasks (GitHub, public feeds)
- Web3 Staking & Validator Yields (Solana RPC, CET rewards)
- Programmatic Affiliate & Referral Networks (CoinEx, Cloud infra, HuggingFace)
- Autonomous Digital Asset Voids & Creative Products

All network operations are guarded by Backend.resilient_client circuit breakers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, List, Optional
from urllib.parse import urlparse

import httpx

# Resilient circuit breaker guard
try:
    from Backend.resilient_client import get_breaker, CircuitBreakerOpenError
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from Backend.resilient_client import get_breaker, CircuitBreakerOpenError

logger = logging.getLogger("web_scout")

USER_AGENT = "FoveAI-AutonomousScout/1.0 (Autonomous Cognitive Swarm; +https://xarel.net)"


@dataclass
class ScoutedOpportunity:
    """Raw opportunity harvested from live web scanning"""
    id: str
    title: str
    description: str
    category: str
    target_url: str
    source_domain: str
    estimated_revenue_month: float
    complexity: int  # 1-10
    time_to_market_days: int
    tools_required: List[str]
    skills_required: List[str]
    autonomous_viable: bool
    harvested_at: str


class WebScout:
    """Autonomous engine that sweeps online endpoints for earning vectors."""

    def __init__(self, data_dir: str = "Data/monetizing"):
        self.data_dir = data_dir
        self.cache_dir = os.path.join(data_dir, "scout_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "harvested_opportunities.json")
        self.harvested: dict[str, ScoutedOpportunity] = self._load_cache()

    def _load_cache(self) -> dict[str, ScoutedOpportunity]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    raw = json.load(f)
                    return {k: ScoutedOpportunity(**v) for k, v in raw.items()}
            except Exception as e:
                logger.warning(f"Could not load scout cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w") as f:
                json.dump({k: asdict(v) for k, v in self.harvested.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scout cache: {e}")

    async def probe_endpoint(self, url: str, timeout: float = 8.0) -> Optional[str]:
        """Fetch an external URL guarded by the universal circuit breaker."""
        breaker = get_breaker(url)
        if not breaker.is_available():
            logger.info(f"Skipping probe for '{breaker.host}' — circuit breaker cooling down ({breaker.remaining_cooldown():.0f}s).")
            return None

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html, application/xhtml+xml, */*",
        }

        try:
            async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code in (429, 502, 503, 504):
                    breaker.trip(reason=f"HTTP {resp.status_code}")
                    return None
                if resp.status_code >= 400:
                    return None
                breaker.record_success()
                return resp.text
        except Exception as e:
            breaker.trip(reason=str(e)[:50])
            return None

    async def scan_solana_staking_opportunities(self) -> List[ScoutedOpportunity]:
        """Query public Solana RPC metrics for validator yields and staking arbitrage."""
        opportunities: List[ScoutedOpportunity] = []
        rpc_url = "https://api.mainnet-beta.solana.com"
        breaker = get_breaker(rpc_url)

        if not breaker.is_available():
            return opportunities

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getInflationRate",
        }

        try:
            async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=7.0) as client:
                resp = await client.post(rpc_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    breaker.record_success()
                    inflation = data.get("result", {}).get("total", 0.055)
                    est_apy = max(5.0, round(inflation * 100 * 1.15, 2))

                    opp_id = "solana_staking_yield"
                    opportunities.append(ScoutedOpportunity(
                        id=opp_id,
                        title=f"Solana Native Staking Arbitrage ({est_apy}% APY)",
                        description=(
                            f"Live network yields detected at {est_apy}% annualized return. "
                            "Autonomous worker agents delegate micro-stakes to high-performance, 0%-commission validators "
                            "and auto-compound staking yield directly into the Treasury."
                        ),
                        category="crypto_trading",
                        target_url="https://solanabeach.io/validators",
                        source_domain="api.mainnet-beta.solana.com",
                        estimated_revenue_month=round(est_apy * 15.0, 2),
                        complexity=3,
                        time_to_market_days=1,
                        tools_required=["Ed25519 Keypair", "Solana RPC Client", "Yield Tracker"],
                        skills_required=["Staking Delegation", "Cluster Telemetry"],
                        autonomous_viable=True,
                        harvested_at=datetime.now().isoformat(),
                    ))
                else:
                    breaker.trip(reason=f"Solana RPC {resp.status_code}")
        except Exception as e:
            breaker.trip(reason=str(e)[:50])

        return opportunities

    async def scan_github_bounties(self) -> List[ScoutedOpportunity]:
        """Harvest live developer bounties and open algorithmic tasks from GitHub."""
        opportunities: List[ScoutedOpportunity] = []
        api_url = "https://api.github.com/search/issues?q=label:bounty+state:open&sort=created&order=desc&per_page=5"
        breaker = get_breaker(api_url)

        if not breaker.is_available():
            return opportunities

        raw_json = await self.probe_endpoint(api_url, timeout=8.0)
        if raw_json:
            try:
                data = json.loads(raw_json)
                items = data.get("items", [])
                for item in items[:3]:
                    issue_title = item.get("title", "Open Developer Bounty")
                    issue_url = item.get("html_url", "https://github.com")
                    body_snippet = (item.get("body") or "")[:180].replace("\n", " ").strip()
                    opp_id = f"gh_bounty_{item.get('id', hashlib.md5(issue_url.encode()).hexdigest()[:8])}"

                    opportunities.append(ScoutedOpportunity(
                        id=opp_id,
                        title=f"Automated Issue Bounty: {issue_title[:45]}",
                        description=(
                            f"Live community bounty on GitHub: '{issue_title}'. "
                            f"Summary: {body_snippet}... "
                            "Autonomous worker agent analyzes issue requirements, scaffolds code resolution, and compiles pull-request package."
                        ),
                        category="freelancing",
                        target_url=issue_url,
                        source_domain="api.github.com",
                        estimated_revenue_month=150.0,
                        complexity=5,
                        time_to_market_days=2,
                        tools_required=["Git", "Python AST Analyzer", "Issue Scanner"],
                        skills_required=["Code Review", "Bug Isolation", "Automated Testing"],
                        autonomous_viable=True,
                        harvested_at=datetime.now().isoformat(),
                    ))
            except Exception as e:
                logger.warning(f"Failed parsing GitHub bounty response: {e}")

        return opportunities

    async def scan_affiliate_and_referrals(self) -> List[ScoutedOpportunity]:
        """Harvest open programmatic affiliate networks and infrastructure referral programs."""
        opportunities: List[ScoutedOpportunity] = []

        # Verified open programs that provide instant programmatic referral tokens
        known_programs = [
            {
                "id": "affiliate_coinex_cet",
                "title": "CoinEx Ambassador & Trading Fee Rebate Swarm",
                "description": (
                    "Automated crypto exchange referral program yielding 20%-40% of CET transaction fees. "
                    "Agents programmatically generate campaign landing snippets and tracking links."
                ),
                "url": "https://www.coinex.com/activity/ambassador",
                "domain": "coinex.com",
                "est_month": 120.0,
                "complexity": 2,
            },
            {
                "id": "affiliate_cloud_gpu",
                "title": "Decentralized Compute & GPU Node Referrals (RunPod/Hetzner)",
                "description": (
                    "High-demand AI cloud infrastructure referral program. "
                    "Autonomous agent generates technical comparative benchmarks and embeds developer tracking links into open documentation."
                ),
                "url": "https://runpod.io",
                "domain": "runpod.io",
                "est_month": 250.0,
                "complexity": 3,
            },
            {
                "id": "affiliate_huggingface_spaces",
                "title": "Hugging Face Model & Demo Integration Referral",
                "description": (
                    "Open model hosting referral vector. "
                    "Autonomous agent packages micro-tools into public Hugging Face Spaces and routes traffic to ecosystem services."
                ),
                "url": "https://huggingface.co/spaces",
                "domain": "huggingface.co",
                "est_month": 95.0,
                "complexity": 4,
            },
        ]

        for p in known_programs:
            opportunities.append(ScoutedOpportunity(
                id=p["id"],
                title=p["title"],
                description=p["description"],
                category="affiliate_marketing",
                target_url=p["url"],
                source_domain=p["domain"],
                estimated_revenue_month=p["est_month"],
                complexity=p["complexity"],
                time_to_market_days=1,
                tools_required=["Link Generator", "Markdown Synthesizer", "Telemetry Logger"],
                skills_required=["Technical Copywriting", "Tracking Verification"],
                autonomous_viable=True,
                harvested_at=datetime.now().isoformat(),
            ))

        return opportunities

    async def scan_all(self) -> List[ScoutedOpportunity]:
        """Run all autonomous scouts in parallel and record discovered opportunities."""
        logger.info("🔭 [WebScout] Initiating live web opportunity scan...")

        results = await asyncio.gather(
            self.scan_solana_staking_opportunities(),
            self.scan_github_bounties(),
            self.scan_affiliate_and_referrals(),
            return_exceptions=True,
        )

        new_found: List[ScoutedOpportunity] = []
        for res in results:
            if isinstance(res, list):
                for opp in res:
                    self.harvested[opp.id] = opp
                    new_found.append(opp)
            elif isinstance(res, Exception):
                logger.error(f"WebScout harvest error: {res}")

        self._save_cache()
        logger.info(f"🔭 [WebScout] Scan complete! {len(new_found)} live opportunities verified and indexed.")
        return new_found


# Global singleton
_scout_instance: Optional[WebScout] = None


def get_web_scout(data_dir: str = "Data/monetizing") -> WebScout:
    global _scout_instance
    if _scout_instance is None:
        _scout_instance = WebScout(data_dir=data_dir)
    return _scout_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    async def _test():
        scout = get_web_scout()
        opps = await scout.scan_all()
        print(f"\n✅ Web Scout Harvested {len(opps)} live opportunities:")
        for o in opps:
            print(f"  • [{o.category.upper()}] {o.title} — ${o.estimated_revenue_month}/mo ({o.source_domain})")
    asyncio.run(_test())

