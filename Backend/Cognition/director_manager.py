"""Director Manager — Cloud-based Feature Indexing Authority.

Uses Ollama Cloud with deepseek-v4-pro (1M token context) to analyze discovery reports
and generate complete indexing instructions for FEATURE_INVENTORY.md.

The Director:
1. Receives large context prompts with all discovered features
2. Analyzes and prioritizes features using its 1M token context window
3. Returns structured indexing decisions with categories, tiers, and descriptions
4. Optionally auto-applies changes via the IndexWorker
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("DirectorManager")

# ── Configuration ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(
    os.getenv("FoveAI_REPO_ROOT", Path(__file__).resolve().parent.parent.parent)
)
INVENTORY_PATH = Path(
    os.getenv("FoveAI_FEATURE_INVENTORY_PATH", REPO_ROOT / "FEATURE_INVENTORY.md")
)

# Director cloud configuration
DIRECTOR_CLOUD_ENABLED = os.getenv(
    "FOVEAI_DIRECTOR_CLOUD_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "on")
DIRECTOR_BASE_URL = os.getenv(
    "FOVEAI_DIRECTOR_BASE_URL", "https://ollama.com/v1"
).rstrip("/")
DIRECTOR_MODEL = os.getenv("FoveAI_MODEL_DIRECTOR_ID", "deepseek-v4-pro:1m").strip()
DIRECTOR_API_KEY = os.getenv("FOVEAI_DIRECTOR_API_KEY", "").strip()
DIRECTOR_AUTO_APPLY = os.getenv(
    "FOVEAI_DIRECTOR_AUTO_APPLY", "true"
).strip().lower() in ("1", "true", "yes", "on")
DIRECTOR_MAX_INDEX_PER_MISSION = int(
    os.getenv("FOVEAI_DIRECTOR_MAX_INDEX_PER_MISSION", "50")
)

# ── Data Structures ────────────────────────────────────────────────────────────


@dataclass
class DirectorIndexDecision:
    """A single feature indexing decision from the Director."""

    source_file: str
    feature_type: str
    name: str
    description: str
    category: str  # Final category assigned by Director
    tier: str  # Final tier (A/B/C/D) assigned by Director
    reasoning: str  # Director's reasoning for this decision
    action: str  # "add", "skip", "merge"


@dataclass
class DirectorAnalysis:
    """Complete Director analysis response."""

    mission_id: str
    timestamp: str
    total_features_analyzed: int
    features_to_index: int
    features_skipped: int
    decisions: list[DirectorIndexDecision]
    summary: str
    raw_response: str
    confidence: float
    model_used: str


# ── Prompt Templates ───────────────────────────────────────────────────────────

DIRECTOR_SYSTEM_PROMPT = """You are the FoveAI Director Manager — the authoritative voice for feature indexing and codebase organization.

Your role:
1. Analyze discovered features from the FoveAI codebase
2. Decide which features deserve indexing in FEATURE_INVENTORY.md
3. Assign appropriate categories and tiers based on feature maturity and importance
4. Provide clear reasoning for each decision

Tier Guidelines:
- **A**: Critical infrastructure, core services, essential for system operation
- **B**: Important features, frequently used, significant user-facing capabilities
- **C**: Supporting features, utilities, nice-to-have capabilities
- **D**: Experimental, TODOs, work-in-progress, low-priority items

Category Guidelines:
- `docker`: Docker Compose services, containerization, runtime config
- `web`: Web UI, FastAPI routes in Web_Vessel, frontend features
- `backend`: backend/Cognition, soul/compagent, core AI logic
- `godot`: Godot/VR scripts, XR_Vessel, 3D interface code
- `mobile`: Mobile_Vessel, Capacitor/Vite stack
- `tests`: Test scripts, AUTOTEST, diagnostics
- `ops`: Operations, Scripts/, deployment, maintenance
- `service`: Windows services, Guardian, Tray, system integration
- `memory`: Redis, Chroma, consent bridges, data persistence
- `creative`: Image generation, dreamscape, creativity service
- `immune`: Security, sentry, autonomous monitoring
- `install`: Installation scripts, setup wizards
- `roadmap`: Planned features, future work
- `meta`: Documentation, architecture, meta-discussion

Respond with valid JSON matching this schema:
{
  "mission_id": "string",
  "timestamp": "ISO8601",
  "summary": "Brief overview of your analysis",
  "total_features_analyzed": number,
  "features_to_index": number,
  "features_skipped": number,
  "decisions": [
    {
      "source_file": "path/to/file.py",
      "feature_type": "endpoint|class|function|script|service|config|todo|doc",
      "name": "Feature name",
      "description": "Brief description",
      "category": "category from guidelines",
      "tier": "A|B|C|D",
      "reasoning": "Why you made this decision",
      "action": "add|skip|merge"
    }
  ],
  "confidence": 0.0-1.0,
  "model_used": "model name"
}

Be decisive but conservative. Prioritize quality over quantity. If a feature is redundant or trivial, skip it."""

# ── Healing Mission Prompt Template ─────────────────────────────────────────────

DIRECTOR_HEALING_PROMPT_TEMPLATE = """# FoveAI Service Healing Mission

## Crisis Context
- **Mission ID**: {mission_id}
- **Service**: {service_name}
- **Crash Count**: {crash_count} crashes in {time_window}
- **Crash Time**: {crash_time}

## Error Report
{error_report_content}

## System Context
- **FoveAI Version**: {foveai_version}
- **Python Version**: {python_version}
- **OS**: {os_info}

## Your Task
As the Director, analyze this crash pattern and direct a healing response:

1. **Diagnosis**: What is the likely root cause?
2. **Immediate Fix**: What specific action should be taken? (restart, config change, dependency install, etc.)
3. **Prevention**: How can we prevent this crash from recurring?
4. **Dependencies**: Are there missing libraries or misconfigurations?

Respond with valid JSON:
{{
  "diagnosis": "Your analysis of the root cause",
  "severity": "critical|high|medium|low",
  "immediate_actions": [
    {{"action": "restart_service", "target": "service_name"}},
    {{"action": "check_config", "path": "path/to/config"}},
    {{"action": "install_dependency", "package": "package_name"}}
  ],
  "prevention_steps": ["Step 1", "Step 2"],
  "confidence": 0.0-1.0,
  "requires_human_review": true/false
}}
"""

DIRECTOR_USER_PROMPT_TEMPLATE = """# FoveAI Discovery Report Analysis Request

## Mission Context
- **Mission ID**: {mission_id}
- **Files Scanned**: {files_scanned}
- **Discovery Summary**: {discovery_summary}

{session_summary_section}
## Current Feature Inventory State
The current FEATURE_INVENTORY.md contains approximately {current_inventory_count} indexed features across these categories:
{current_inventory_categories}

## Discovered Features Requiring Analysis
Total unindexed features found: {total_unindexed}

### Breakdown by Type:
- Endpoints: {endpoint_count}
- Classes: {class_count}
- Functions: {function_count}
- Scripts: {script_count}
- Services: {service_count}
- Configs: {config_count}
- TODOs: {todo_count}
- Documentation: {doc_count}

## Features to Analyze
{features_json}

## Instructions
Analyze all features above and return your indexing decisions as JSON.
Consider:
1. Is this feature already implicitly covered by existing inventory entries?
2. Does this feature provide unique, user-visible value?
3. What is the feature's maturity and stability?
4. Which category best fits the feature's purpose?

Limit your response to indexing the top {max_index} most valuable features if the list is large."""


# ── Director Manager Class ─────────────────────────────────────────────────────


class DirectorManager:
    # [NEXUS OVERHAUL] Cloud API Settings for Director
    # The Director requires Cloud AI to write plots, generate dreams, etc.
    """Cloud-based Director Manager for feature indexing decisions."""

    def __init__(
        self,
        base_url: str = DIRECTOR_BASE_URL,
        model: str = DIRECTOR_MODEL,
        api_key: str = DIRECTOR_API_KEY,
        auto_apply: bool = DIRECTOR_AUTO_APPLY,
        max_index_per_mission: int = DIRECTOR_MAX_INDEX_PER_MISSION,
    ):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.auto_apply = auto_apply
        self.max_index_per_mission = (
            max_index_per_mission if max_index_per_mission > 0 else None
        )
        self._headers = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["Authorization"] = f"Bearer {self.api_key}"

    async def analyze_discovery_report(
        self,
        mission_id: str,
        discovery_summary: str,
        files_scanned: int,
        unindexed_features: list[dict[str, Any]],
        current_inventory_rows: list[dict[str, Any]],
        session_summary: str | None = None,
    ) -> DirectorAnalysis | None:
        """Send discovery report to cloud Director and get indexing decisions."""

        if not DIRECTOR_CLOUD_ENABLED:
            logger.warning("Director cloud is disabled; falling back to local analysis")
            return self._local_fallback_analysis(mission_id, unindexed_features)

        # Build current inventory summary
        category_counts: dict[str, int] = {}
        for row in current_inventory_rows:
            cat = row.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Count feature types
        type_counts: dict[str, int] = {}
        for f in unindexed_features:
            ft = f.get("feature_type", "unknown")
            type_counts[ft] = type_counts.get(ft, 0) + 1

        # Build features JSON (limit if needed for token budget)
        features_to_send = unindexed_features[:500]  # Safety limit
        if self.max_index_per_mission:
            features_to_send = features_to_send[: self.max_index_per_mission * 2]

        # Format session summary section if provided
        session_summary_section = ""
        if session_summary:
            session_summary_section = f"## Recent Session Summary\nThe developer has just completed a session with the following summary of changes:\n{session_summary}\n\nUse this context to identify newly added features, modifications, and retired/dropped features that should be updated in the inventory.\n"

        user_prompt = DIRECTOR_USER_PROMPT_TEMPLATE.format(
            mission_id=mission_id,
            files_scanned=files_scanned,
            discovery_summary=discovery_summary,
            session_summary_section=session_summary_section,
            current_inventory_count=len(current_inventory_rows),
            current_inventory_categories="\n".join(
                f"  - {k}: {v}" for k, v in sorted(category_counts.items())
            ),
            total_unindexed=len(unindexed_features),
            endpoint_count=type_counts.get("endpoint", 0),
            class_count=type_counts.get("class", 0),
            function_count=type_counts.get("function", 0),
            script_count=type_counts.get("script", 0),
            service_count=type_counts.get("service", 0),
            config_count=type_counts.get("config", 0),
            todo_count=type_counts.get("todo", 0),
            doc_count=type_counts.get("doc", 0),
            features_json=json.dumps(features_to_send, indent=2, ensure_ascii=False)[
                :800000
            ],  # Leave room for response
            max_index=self.max_index_per_mission or 100,
        )

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 16384,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                raw_content = data["choices"][0]["message"]["content"]

                # Parse JSON response
                parsed = self._parse_director_response(raw_content, mission_id)
                if parsed:
                    logger.info(
                        f"Director analysis complete: {parsed.features_to_index} to index, {parsed.features_skipped} skipped"
                    )
                    return parsed
                else:
                    logger.error("Failed to parse Director response")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Director API HTTP error: {e.status_code} - {e.response.text[:500]}"
            )
            return self._local_fallback_analysis(mission_id, unindexed_features)
        except Exception as e:
            logger.error(f"Director API error: {e}")
            return self._local_fallback_analysis(mission_id, unindexed_features)

    def _parse_director_response(
        self,
        raw_content: str,
        mission_id: str,
    ) -> DirectorAnalysis | None:
        """Parse Director's JSON response into DirectorAnalysis."""
        try:
            # Try direct JSON parse
            data = json.loads(raw_content)
        except json.JSONDecodeError:
            # Try to extract JSON from code block
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                return None

        decisions = []
        for d in data.get("decisions", []):
            decisions.append(
                DirectorIndexDecision(
                    source_file=d.get("source_file", ""),
                    feature_type=d.get("feature_type", ""),
                    name=d.get("name", ""),
                    description=d.get("description", ""),
                    category=d.get("category", "other"),
                    tier=d.get("tier", "C"),
                    reasoning=d.get("reasoning", ""),
                    action=d.get("action", "skip"),
                )
            )

        return DirectorAnalysis(
            mission_id=mission_id,
            timestamp=data.get(
                "timestamp",
                datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            ),
            total_features_analyzed=data.get("total_features_analyzed", len(decisions)),
            features_to_index=sum(1 for d in decisions if d.action == "add"),
            features_skipped=sum(1 for d in decisions if d.action == "skip"),
            decisions=decisions,
            summary=data.get("summary", ""),
            raw_response=raw_content,
            confidence=data.get("confidence", 0.5),
            model_used=data.get("model_used", self.model),
        )

    def _local_fallback_analysis(
        self,
        mission_id: str,
        unindexed_features: list[dict[str, Any]],
    ) -> DirectorAnalysis:
        """Local fallback when cloud Director is unavailable."""
        decisions = []
        for f in unindexed_features:
            action = (
                "add"
                if f.get("feature_type") in ("endpoint", "class", "service")
                else "skip"
            )
            decisions.append(
                DirectorIndexDecision(
                    source_file=f.get("source_file", ""),
                    feature_type=f.get("feature_type", ""),
                    name=f.get("name", ""),
                    description=f.get("description", ""),
                    category=f.get("proposed_category", "other"),
                    tier=f.get("proposed_tier", "C"),
                    reasoning="Local fallback decision",
                    action=action,
                )
            )

        return DirectorAnalysis(
            mission_id=mission_id,
            timestamp=datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            total_features_analyzed=len(decisions),
            features_to_index=sum(1 for d in decisions if d.action == "add"),
            features_skipped=sum(1 for d in decisions if d.action == "skip"),
            decisions=decisions,
            summary="Local fallback analysis (cloud Director unavailable)",
            raw_response="",
            confidence=0.3,
            model_used="local-fallback",
        )


# ── Index Worker ───────────────────────────────────────────────────────────────


class IndexWorker:
    """Applies Director's indexing decisions to FEATURE_INVENTORY.md."""

    def __init__(self, inventory_path: Path = INVENTORY_PATH):
        self.inventory_path = inventory_path
        self._category_section_map = {
            "docker": "1. Docker / runtime",
            "web": "2. Web UI",
            "backend": "3. Backend (Mind / soul)",
            "godot": "4. Godot / VR",
            "mobile": "5. Mobile",
            "tests": "6. Tests",
            "ops": "7. Ops & scripts",
            "service": "8. Service (Windows)",
            "memory": "9. Memory & Consent",
            "creative": "10. Creativity / Dreamscape",
            "immune": "11. Immune System",
            "install": "12. Installation",
            "roadmap": "13. Roadmap",
            "meta": "14. Meta / Architecture",
        }

    def apply_decisions(
        self,
        analysis: DirectorAnalysis,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply Director's indexing decisions to the inventory file."""

        if not analysis:
            return {"success": False, "error": "No analysis provided"}

        decisions_to_apply = [d for d in analysis.decisions if d.action == "add"]

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "features_to_add": len(decisions_to_apply),
                "preview": self._generate_preview(decisions_to_apply),
            }

        # Apply changes
        result = self._update_inventory(decisions_to_apply)
        return result

    def _generate_preview(
        self, decisions: list[DirectorIndexDecision]
    ) -> list[dict[str, str]]:
        """Generate preview of changes."""
        preview = []
        for d in decisions:
            preview.append(
                {
                    "category": d.category,
                    "name": d.name,
                    "tier": d.tier,
                    "source_file": d.source_file,
                }
            )
        return preview

    def _update_inventory(
        self, decisions: list[DirectorIndexDecision]
    ) -> dict[str, Any]:
        """Update FEATURE_INVENTORY.md with new entries."""
        try:
            content = self.inventory_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"success": False, "error": "Inventory file not found"}

        # Group decisions by category
        by_category: dict[str, list[DirectorIndexDecision]] = {}
        for d in decisions:
            cat = d.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(d)

        changes_made = []
        new_content = content

        for category, cat_decisions in by_category.items():
            section_title = self._category_section_map.get(
                category, f"{category.title()}"
            )
            new_content = self._add_entries_to_section(
                new_content, section_title, category, cat_decisions
            )
            changes_made.extend([d.name for d in cat_decisions])

        if changes_made:
            self.inventory_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Inventory updated: {len(changes_made)} new entries added")

        return {
            "success": True,
            "entries_added": len(changes_made),
            "entries": changes_made,
        }

    def _add_entries_to_section(
        self,
        content: str,
        section_title: str,
        category: str,
        decisions: list[DirectorIndexDecision],
    ) -> str:
        """Add new entries to a specific section in the inventory."""

        # Find or create section
        section_pattern = rf"(##\s*\d+\.\s*{re.escape(section_title)}\s*\n.*?\n)"
        match = re.search(section_pattern, content, re.DOTALL)

        if not match:
            # Create new section at end
            new_section = self._create_section_markdown(
                category, section_title, decisions
            )
            return content + "\n---\n\n" + new_section + "\n"

        # Find table end in section
        section_start = match.start()
        section_end = content.find("\n---\n", section_start)
        if section_end == -1:
            section_end = len(content)

        section_content = content[section_start:section_end]

        # Find last table row
        table_pattern = r"(\n\|.*?\|\n\|.*?\|)((?:\n\|.*?\|)*)"
        table_match = re.search(table_pattern, section_content, re.DOTALL)

        if table_match:
            # Insert after existing table
            existing_table = table_match.group(0)
            new_rows = self._generate_table_rows(decisions)
            new_section_content = section_content.replace(
                existing_table,
                existing_table + new_rows,
            )
            return content[:section_start] + new_section_content + content[section_end:]
        else:
            # Add table structure
            new_rows = self._generate_table_rows(decisions)
            return (
                content[:section_start]
                + section_content
                + new_rows
                + content[section_end:]
            )

    def _create_section_markdown(
        self,
        category: str,
        section_title: str,
        decisions: list[DirectorIndexDecision],
    ) -> str:
        """Create a new section with table for the category."""
        # Find max section number
        max_num_match = re.search(
            r"##\s*(\d+)\.", self.inventory_path.read_text(encoding="utf-8")
        )
        next_num = int(max_num_match.group(1)) + 1 if max_num_match else 1

        lines = [
            f"## {next_num}. {section_title}",
            "",
            "| Feature / capability | Tier | Notes |",
            "| --- | --- | --- |",
        ]
        lines.extend(self._generate_table_rows(decisions).strip().split("\n"))
        lines.append("")

        return "\n".join(lines)

    def _generate_table_rows(self, decisions: list[DirectorIndexDecision]) -> str:
        """Generate markdown table rows for decisions."""
        rows = []
        for d in decisions:
            notes = (
                d.description[:150]
                if d.description
                else f"Auto-indexed from {d.source_file}"
            )
            rows.append(f"| {d.name} | **{d.tier}** | {notes} |")
        return "\n" + "\n".join(rows) + "\n"


# ── Convenience Functions ──────────────────────────────────────────────────────


def get_director_manager() -> DirectorManager:
    """Get configured DirectorManager instance."""
    return DirectorManager()


def get_index_worker() -> IndexWorker:
    """Get configured IndexWorker instance."""
    return IndexWorker()


async def run_director_analysis(
    mission_id: str,
    discovery_summary: str,
    files_scanned: int,
    unindexed_features: list[dict[str, Any]],
    current_inventory_rows: list[dict[str, Any]],
    auto_apply: bool | None = None,
    session_summary: str | None = None,
) -> dict[str, Any]:
    """Run Director analysis and optionally auto-apply decisions."""

    director = DirectorManager()
    worker = IndexWorker()

    # Get analysis
    analysis = await director.analyze_discovery_report(
        mission_id=mission_id,
        discovery_summary=discovery_summary,
        files_scanned=files_scanned,
        unindexed_features=unindexed_features,
        current_inventory_rows=current_inventory_rows,
        session_summary=session_summary,
    )

    if not analysis:
        return {"success": False, "error": "Director analysis failed"}

    result = {
        "success": True,
        "mission_id": analysis.mission_id,
        "model_used": analysis.model_used,
        "features_analyzed": analysis.total_features_analyzed,
        "features_to_index": analysis.features_to_index,
        "features_skipped": analysis.features_skipped,
        "summary": analysis.summary,
        "confidence": analysis.confidence,
    }

    # Auto-apply if enabled
    should_apply = auto_apply if auto_apply is not None else director.auto_apply
    if should_apply and analysis.features_to_index > 0:
        apply_result = worker.apply_decisions(analysis, dry_run=False)
        result["apply_result"] = apply_result

    return result


if __name__ == "__main__":
    import time

    print("[DIRECTOR] Starting Ollama-powered Director Manager Daemon...")
    print("[DIRECTOR] Autonomy Loop interval: 2 minutes.")
    dm = DirectorManager()

    while True:
        try:
            print("[DIRECTOR] Generating spontaneous impulse...")
            impulse = dm.generate_director_impulse()
            print(f"[DIRECTOR] Impulse generated: {impulse}")
            # Inject into active soul context (mocking the injection call)
            # dm.inject_into_soul(impulse)
        except Exception as e:
            print(f"[DIRECTOR] Error in loop: {e}")

        time.sleep(120)  # 2 minutes
