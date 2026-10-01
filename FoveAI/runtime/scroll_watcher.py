r"""
scroll_watcher.py — The Dragon's Candle
========================================
Watches the scrolls/ directory for new knowledge.
At runtime, loads all .xrlf scroll files and injects them
into the system prompt as additional context for the dragon.

The dragon's body is frozen. But its wisdom grows
every time a new scroll is placed in the cave.

Usage:
    watcher = ScrollWatcher(Path("scrolls/"))
    scrolls = watcher.gather()  # returns all scroll texts
    prompt = watcher.build_scroll_context(scrolls)  # formatted for injection
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Scroll:
    """A single dragon scroll — a unit of drop-in knowledge."""

    path: Path
    domain: str
    priority: str
    scroll_id: str
    content: str
    modified: float


class ScrollWatcher:
    """
    Watches the scrolls/ directory and gathers all .xrlf scroll files.
    Scrolls are plain text with <scroll> tags — no binary, no GGUF.
    The dragon reads them at startup and whenever the cave is refreshed.
    """

    # Priority ordering — sacred scrolls first, then high, then normal
    PRIORITY_ORDER = {"sacred": 0, "high": 1, "normal": 2, "low": 3}

    def __init__(self, scrolls_dir: Path):
        self.scrolls_dir = Path(scrolls_dir)
        self._cache: dict[str, Scroll] = {}
        self._last_scan: float = 0

    def gather(self, force_rescan: bool = False) -> list[Scroll]:
        """
        Scan the scrolls directory and return all scrolls,
        ordered by priority then by filename.
        """
        if not self.scrolls_dir.exists():
            return []

        # Check if rescan is needed
        latest_mtime = max(
            (
                f.stat().st_mtime
                for f in self.scrolls_dir.rglob("*.xrlf")
                if f.is_file()
            ),
            default=0,
        )
        if not force_rescan and latest_mtime <= self._last_scan and self._cache:
            return list(self._cache.values())

        # Scan all scroll files
        scrolls: list[Scroll] = []
        for scroll_path in sorted(self.scrolls_dir.rglob("*.xrlf")):
            if not scroll_path.is_file():
                continue
            content = scroll_path.read_text(encoding="utf-8")
            meta = self._parse_scroll_meta(content)
            scrolls.append(
                Scroll(
                    path=scroll_path,
                    domain=meta.get("domain", "unknown"),
                    priority=meta.get("priority", "normal"),
                    scroll_id=meta.get("id", scroll_path.stem),
                    content=content,
                    modified=scroll_path.stat().st_mtime,
                )
            )

        # Sort by priority, then by path
        scrolls.sort(
            key=lambda s: (self.PRIORITY_ORDER.get(s.priority, 3), str(s.path))
        )

        # Update cache
        self._cache = {s.scroll_id: s for s in scrolls}
        self._last_scan = latest_mtime

        return scrolls

    def build_scroll_context(
        self, scrolls: list[Scroll] | None = None, max_chars: int = 8000
    ) -> str:
        """
        Build a text block from all scrolls, formatted for injection
        into the system prompt. Truncates to max_chars to respect
        context window limits.
        """
        if scrolls is None:
            scrolls = self.gather()

        if not scrolls:
            return ""

        parts = ["# DRAGON_SCROLLS — Knowledge from the cave"]
        total = len(parts[0])

        for scroll in scrolls:
            # Clean the scroll content — remove the <scroll> wrapper
            clean = self._clean_scroll(scroll.content)
            header = f"\n## Scroll: {scroll.scroll_id} (domain={scroll.domain})"

            block = f"{header}\n{clean}"
            if total + len(block) > max_chars:
                # Truncate this scroll
                remaining = max_chars - total - len(header) - 50
                if remaining > 200:
                    block = f"{header}\n{clean[:remaining]}...\n[scroll truncated]"
                else:
                    break

            parts.append(block)
            total += len(block)

        return "\n".join(parts)

    def _parse_scroll_meta(self, content: str) -> dict[str, str]:
        """Extract id, domain, priority from the <scroll> opening tag."""
        meta = {}
        # Look for <scroll id="..." domain="..." priority="...">
        first_line = content.split("\n")[0] if content else ""
        for field in ["id", "domain", "priority"]:
            marker = f'{field}="'
            if marker in first_line:
                start = first_line.index(marker) + len(marker)
                end = first_line.index('"', start)
                meta[field] = first_line[start:end]
        return meta

    def _clean_scroll(self, content: str) -> str:
        """Remove the <scroll> wrapper tags, keep the inner text."""
        lines = content.split("\n")
        # Skip the first line (<scroll ...>) and last meaningful line ([SCROLL_END])
        if lines and lines[0].strip().startswith("<scroll"):
            lines = lines[1:]
        # Remove [SCROLL_END] if present
        lines = [l for l in lines if l.strip() != "[SCROLL_END]"]
        if lines and lines[-1].strip() == "</scroll>":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def watch(self) -> bool:
        """
        Check if any scrolls have been added or modified since last scan.
        Returns True if the cave has new knowledge for the dragon.
        """
        if not self.scrolls_dir.exists():
            return False
        latest = max(
            (
                f.stat().st_mtime
                for f in self.scrolls_dir.rglob("*.xrlf")
                if f.is_file()
            ),
            default=0,
        )
        return latest > self._last_scan

    def list_scrolls(self) -> list[dict]:
        """Return a summary of all scrolls in the cave."""
        scrolls = self.gather()
        return [
            {
                "id": s.scroll_id,
                "domain": s.domain,
                "priority": s.priority,
                "path": str(s.path.relative_to(self.scrolls_dir)),
                "chars": len(s.content),
            }
            for s in scrolls
        ]
