"""
Smart Context Manager — Tiered context window governance for the FoveAI Proxy.

Orchestrates ContextStripper (Tier 1 regex noise removal) with higher-tier
strategies (history truncation, full checkpoint) based on live token budgets.

Tier ladder (ascending aggression):
  Tier 0  NONE               — pass through untouched
  Tier 1  STRIP_NOISE         — regex thinking/dedup (delegated to ContextStripper)
  Tier 2  SUMMARIZE_OLD_TURNS — fold mid-history into compact summary markers
  Tier 3  TRUNCATE_HISTORY    — hard truncate to TIER_3_TARGET_TOKENS (default 30k)
  Tier 4  FULL_CHECKPOINT     — collapse everything except last N turns into a
                                single checkpoint block (~15% of current size)

The proxy calls:
  await smart_context_manager.start()
  rec = await smart_context_manager.report_tokens(session_id, token_count, messages)
  if rec.action.startswith("cut_"):
      processed, meta = await smart_context_manager.apply_cutting_strategy(session_id, messages)
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from context_stripper import ContextStripper, estimate_tokens

logger = logging.getLogger("forge.smart_context")


# ── Configuration ───────────────────────────────────────────────────────

class ContextConfig:
    """Central tunable budget. Override via env vars at startup."""

    # Session target (the "comfortable" working budget)
    TARGET_TOKENS: int = int(os.environ.get("FoveAI_SMARTCTX_TARGET", "40000"))

    # Soft warning threshold (start considering cuts)
    WARN_THRESHOLD: float = 0.75  # 75% of target

    # Hard trigger thresholds per tier (fraction of target)
    TIER_2_FRAC: float = 0.90   # summarize when >= 90% of target
    TIER_3_FRAC: float = 1.20   # truncate when >= 120% of target
    TIER_4_FRAC: float = 1.60   # full checkpoint when >= 160% of target

    # NEW: Tier 3 target is now 30k (was ~9k — far too aggressive).
    # A 70k context gets cut to ~30k instead of ~9k, preserving much more
    # working history while still staying under typical 32k-128k limits.
    TIER_3_TARGET_TOKENS: int = int(os.environ.get("FoveAI_SMARTCTX_TIER3_TARGET", "30000"))

    # Tier 4 collapses to ~15% of current size
    TIER_4_KEEP_FRAC: float = 0.15

    # Quality / burst settings
    QUALITY_THRESHOLD_LOW: float = 0.40
    BURST_COOLDOWN_TURNS: int = 4
    BURST_WINDOW_TURNS: int = 3

    # How many recent turns to always preserve
    PRESERVE_LAST: int = int(os.environ.get("FoveAI_SMARTCTX_PRESERVE_LAST", "5"))


class CuttingTier(Enum):
    NONE = 0
    TIER_1_STRIP_NOISE = 1
    TIER_2_SUMMARIZE_OLD = 2
    TIER_3_TRUNCATE_HISTORY = 3
    TIER_4_FULL_CHECKPOINT = 4


class CuttingAction:
    """String constants returned in ContextRecommendation.action."""
    PASS = "pass"
    CUT_TIER_1 = "cut_tier_1_strip"
    CUT_TIER_2 = "cut_tier_2_summarize"
    CUT_TIER_3 = "cut_tier_3_truncate"
    CUT_TIER_4 = "cut_tier_4_checkpoint"
    RESTART = "restart"


# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class ContextRecommendation:
    action: str = CuttingAction.PASS
    tier: CuttingTier = CuttingTier.NONE
    reason: str = ""
    est_before: int = 0
    est_after: int = 0


@dataclass
class BurstMode:
    is_active: bool = False
    turns_remaining: int = 0


@dataclass
class SessionState:
    session_id: str
    target_tokens: int = ContextConfig.TARGET_TOKENS
    last_token_count: int = 0
    turns_since_burst: int = 999
    burst_mode: BurstMode = field(default_factory=BurstMode)
    quality: float = 1.0
    stripper: ContextStripper = field(default_factory=lambda: ContextStripper(
        preserve_last=ContextConfig.PRESERVE_LAST
    ))


# ── Manager ─────────────────────────────────────────────────────────────

class SmartContextManager:
    """Stateful, async-safe manager of per-session context budgets."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._running = False

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        logger.info(
            "SmartContextManager started | target=%d | tier3_target=%d",
            ContextConfig.TARGET_TOKENS,
            ContextConfig.TIER_3_TARGET_TOKENS,
        )

    async def stop(self) -> None:
        self._running = False
        logger.info("SmartContextManager stopped")

    # ── internal helpers ───────────────────────────────────────────────

    def _get_state(self, session_id: str) -> SessionState:
        st = self._sessions.get(session_id)
        if st is None:
            st = SessionState(session_id=session_id)
            self._sessions[session_id] = st
        return st

    def _estimate_total(self, messages: List[Dict]) -> int:
        return sum(estimate_tokens(str(m.get("content", ""))) for m in messages)

    def _determine_tier(self, current: int, target: int) -> CuttingTier:
        if current >= target * ContextConfig.TIER_4_FRAC:
            return CuttingTier.TIER_4_FULL_CHECKPOINT
        if current >= target * ContextConfig.TIER_3_FRAC:
            return CuttingTier.TIER_3_TRUNCATE_HISTORY
        if current >= target * ContextConfig.TIER_2_FRAC:
            return CuttingTier.TIER_2_SUMMARIZE_OLD
        if current >= target * ContextConfig.WARN_THRESHOLD:
            return CuttingTier.TIER_1_STRIP_NOISE
        return CuttingTier.NONE

    def _burst_rec(self, state: SessionState, active: bool, triggered: bool) -> ContextRecommendation:
        if active:
            state.burst_mode.is_active = True
            state.burst_mode.turns_remaining = ContextConfig.BURST_WINDOW_TURNS
            state.turns_since_burst = 0
        return ContextRecommendation(
            action=CuttingAction.PASS,
            tier=CuttingTier.NONE,
            reason="burst_mode_active" if active else "burst_cooldown",
            est_before=state.last_token_count,
            est_after=state.last_token_count,
        )

    # ── public API ─────────────────────────────────────────────────────

    async def report_tokens(
        self,
        session_id: str,
        token_count: int,
        messages: List[Dict],
    ) -> ContextRecommendation:
        """Inspect token usage and recommend a cutting action."""
        async with self._lock:
            state = self._get_state(session_id)
            state.last_token_count = token_count
            state.turns_since_burst += 1

            # Burst handling — skip cutting while in burst window
            if state.burst_mode.is_active:
                state.burst_mode.turns_remaining -= 1
                if state.burst_mode.turns_remaining <= 0:
                    state.burst_mode.is_active = False
                return self._burst_rec(state, active=False, triggered=False)

            burst_triggered = (
                state.turns_since_burst >= ContextConfig.BURST_COOLDOWN_TURNS
                and token_count >= state.target_tokens * 0.85
            )
            if burst_triggered and not state.burst_mode.is_active:
                return self._burst_rec(state, True, True)

            # Determine cutting tier
            tier = self._determine_tier(token_count, state.target_tokens)

            # Low-quality + extreme excess → suggest restart
            if state.quality < ContextConfig.QUALITY_THRESHOLD_LOW and token_count >= state.target_tokens * 0.90:
                return ContextRecommendation(
                    action=CuttingAction.RESTART,
                    tier=CuttingTier.TIER_4_FULL_CHECKPOINT,
                    reason=f"low_quality({state.quality:.2f})_and_excess",
                    est_before=token_count,
                    est_after=int(token_count * ContextConfig.TIER_4_KEEP_FRAC),
                )

            if tier == CuttingTier.NONE:
                return ContextRecommendation(
                    action=CuttingAction.PASS,
                    tier=CuttingTier.NONE,
                    reason="within_budget",
                    est_before=token_count,
                    est_after=token_count,
                )

            # Estimate post-cut size
            if tier == CuttingTier.TIER_3_TRUNCATE_HISTORY:
                est_after = ContextConfig.TIER_3_TARGET_TOKENS
            elif tier == CuttingTier.TIER_4_FULL_CHECKPOINT:
                est_after = int(token_count * ContextConfig.TIER_4_KEEP_FRAC)
            elif tier == CuttingTier.TIER_2_SUMMARIZE_OLD:
                est_after = int(token_count * 0.55)
            else:
                est_after = int(token_count * 0.80)

            action_map = {
                CuttingTier.TIER_1_STRIP_NOISE: CuttingAction.CUT_TIER_1,
                CuttingTier.TIER_2_SUMMARIZE_OLD: CuttingAction.CUT_TIER_2,
                CuttingTier.TIER_3_TRUNCATE_HISTORY: CuttingAction.CUT_TIER_3,
                CuttingTier.TIER_4_FULL_CHECKPOINT: CuttingAction.CUT_TIER_4,
            }

            return ContextRecommendation(
                action=action_map.get(tier, CuttingAction.PASS),
                tier=tier,
                reason=f"tier_{tier.value}_triggered ({token_count} >= threshold)",
                est_before=token_count,
                est_after=est_after,
            )

    async def apply_cutting_strategy(
        self,
        session_id: str,
        messages: List[Dict],
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """Apply the most aggressive needed cutting strategy to the messages."""
        async with self._lock:
            state = self._get_state(session_id)
            current = self._estimate_total(messages)
            tier = self._determine_tier(current, state.target_tokens)

            meta: Dict[str, Any] = {
                "tier": tier.name,
                "tokens_before": current,
                "tokens_after": current,
                "action": CuttingAction.PASS,
            }

            # Tier 1 is always applied first (cheap regex noise removal)
            processed = state.stripper.strip_messages(messages)
            after_strip = self._estimate_total(processed)

            # Re-evaluate tier after stripping
            tier = self._determine_tier(after_strip, state.target_tokens)

            if tier == CuttingTier.NONE:
                meta["tokens_after"] = after_strip
                meta["action"] = CuttingAction.CUT_TIER_1
                return processed, meta

            if tier == CuttingTier.TIER_2_SUMMARIZE_OLD:
                processed = self._summarize_old_turns(processed, state)
                action = CuttingAction.CUT_TIER_2

            elif tier == CuttingTier.TIER_3_TRUNCATE_HISTORY:
                processed = self._truncate_to_target(processed, ContextConfig.TIER_3_TARGET_TOKENS, state)
                action = CuttingAction.CUT_TIER_3

            elif tier == CuttingTier.TIER_4_FULL_CHECKPOINT:
                keep = int(current * ContextConfig.TIER_4_KEEP_FRAC)
                processed = self._truncate_to_target(processed, max(keep, 2000), state, checkpoint=True)
                action = CuttingAction.CUT_TIER_4

            else:
                action = CuttingAction.CUT_TIER_1

            final = self._estimate_total(processed)
            meta["tokens_after"] = final
            meta["action"] = action
            logger.info(
                "SmartContext cut session=%s tier=%s %d→%d tokens",
                session_id, tier.name, current, final,
            )
            return processed, meta

    # ── cutting strategies ─────────────────────────────────────────────

    def _summarize_old_turns(self, messages: List[Dict], state: SessionState) -> List[Dict]:
        """Tier 2: replace old user/assistant pairs with compact summary markers."""
        preserve = ContextConfig.PRESERVE_LAST
        total = len(messages)
        if total <= preserve:
            return messages

        out: List[Dict] = []
        keep_from = total - preserve
        for i, msg in enumerate(messages):
            if i >= keep_from:
                out.append(msg)
                continue
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role in ("user", "assistant") and len(content) > 400:
                nm = dict(msg)
                nm["content"] = f"[ctx-summary] {content[:200]}... ({len(content)} chars folded)"
                out.append(nm)
            else:
                out.append(msg)
        return out

    def _truncate_to_target(
        self,
        messages: List[Dict],
        target_tokens: int,
        state: SessionState,
        checkpoint: bool = False,
    ) -> List[Dict]:
        """Tier 3/4: keep system + last N turns, truncate middle to fit target."""
        if not messages:
            return messages

        preserve = ContextConfig.PRESERVE_LAST
        # Always keep system messages at the front
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= preserve:
            return messages

        preserved = non_system[-preserve:]
        candidate = non_system[:-preserve]

        # Greedy fill from the most recent side of the candidate pool
        kept_middle: List[Dict] = []
        running = sum(estimate_tokens(str(m.get("content", ""))) for m in system_msgs)
        running += sum(estimate_tokens(str(m.get("content", ""))) for m in preserved)

        for msg in reversed(candidate):
            t = estimate_tokens(str(msg.get("content", "")))
            if running + t > target_tokens:
                break
            kept_middle.insert(0, msg)
            running += t

        if checkpoint:
            # Insert a checkpoint marker for the discarded portion
            discarded_count = len(candidate) - len(kept_middle)
            if discarded_count > 0:
                ckpt = {
                    "role": "system",
                    "content": (
                        f"[CONTEXT CHECKPOINT] {discarded_count} prior messages truncated "
                        f"to fit {target_tokens} token budget. Last {preserve} turns preserved."
                    ),
                }
                return system_msgs + [ckpt] + kept_middle + preserved

        return system_msgs + kept_middle + preserved


# ── Singleton ───────────────────────────────────────────────────────────

smart_context_manager = SmartContextManager()