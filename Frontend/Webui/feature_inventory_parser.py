"""Parse FEATURE_INVENTORY.md into JSON for the Web UI feature map."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TABLE_SEP = re.compile(r"^\|?[\s\-:|]+\|?\s*$")
_H2 = re.compile(r"^##\s+(.+)$")
_H3 = re.compile(r"^###\s+(.+)$")
_TIER_CELL = re.compile(r"\*\*([ABCD])(?:/([ABCD]))?\*\*", re.IGNORECASE)
_LEADING_SECTION_NUM = re.compile(r"^(\d+)\.")

_CATEGORY_BY_NUM: dict[int, str] = {
    1: "docker",
    2: "web",
    3: "backend",
    4: "godot",
    5: "mobile",
    6: "tests",
    7: "ops",
    8: "parity",
    9: "roadmap",
    10: "meta",
}

_CATEGORY_LABELS: dict[str, str] = {
    "preamble": "Intro & tiers",
    "docker": "Docker / runtime",
    "web": "Web UI",
    "backend": "Backend",
    "godot": "Godot / VR",
    "mobile": "Mobile",
    "tests": "Tests",
    "ops": "Ops & scripts",
    "parity": "Cross-surface",
    "roadmap": "Gaps & next steps",
    "meta": "Maintenance",
    "other": "Other",
}


def _slug(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:96]


def _category_from_h2_title(title: str) -> str:
    m = _LEADING_SECTION_NUM.match(title.strip())
    if not m:
        return "preamble"
    return _CATEGORY_BY_NUM.get(int(m.group(1)), "other")


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _tiers_from_cell(cell: str) -> list[str]:
    found: list[str] = []
    for m in _TIER_CELL.finditer(cell or ""):
        found.append(m.group(1).upper())
        if m.group(2):
            found.append(m.group(2).upper())
    return found


def _guess_label_column(headers: list[str]) -> int:
    hlow = [h.lower() for h in headers]
    for key in (
        "feature",
        "capability",
        "artifact",
        "item",
        "script / area",
        "script",
        "area",
    ):
        for idx, hn in enumerate(hlow):
            if key in hn:
                return idx
    return 0


def _guess_notes_column(headers: list[str]) -> int | None:
    for idx, hn in enumerate(headers):
        lo = hn.lower()
        if "note" in lo or "suggested" in lo or "direction" in lo:
            return idx
    if len(headers) > 2:
        return len(headers) - 1
    return None


def _parse_table(lines: list[str], start: int) -> tuple[dict[str, Any] | None, int]:
    if start >= len(lines) or not lines[start].strip().startswith("|"):
        return None, 0
    headers = _split_table_row(lines[start])
    if not headers:
        return None, 0
    i = start + 1
    if i < len(lines) and _TABLE_SEP.match(lines[i].strip()):
        i += 1
    rows: list[list[str]] = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        row = _split_table_row(lines[i])
        if any(c.strip() for c in row):
            rows.append(row)
        i += 1
    return {"headers": headers, "rows": rows}, i - start


def _table_to_flat_rows(
    table: dict[str, Any],
    *,
    h2_title: str,
    h3_title: str | None,
    category: str,
) -> list[dict[str, Any]]:
    headers: list[str] = table.get("headers") or []
    rows: list[list[str]] = table.get("rows") or []
    if not headers or not rows:
        return []

    hn = [h.lower() for h in headers]
    if hn[:2] == ["tier", "meaning"]:
        return []

    tier_i = next((idx for idx, h in enumerate(headers) if "tier" in h.lower()), None)
    label_i = _guess_label_column(headers)
    notes_i = _guess_notes_column(headers)

    parity_cols = hn[0] == "capability" and any("web" in h for h in hn)

    out: list[dict[str, Any]] = []
    for row in rows:
        while len(row) < len(headers):
            row.append("")
        label = row[label_i] if label_i < len(row) else ""
        notes = row[notes_i] if notes_i is not None and notes_i < len(row) else ""
        if parity_cols:
            notes = " | ".join(row[i] for i in range(len(row)) if i != label_i)
        tier_cell = row[tier_i] if tier_i is not None and tier_i < len(row) else ""
        tiers = _tiers_from_cell(tier_cell)
        if not tiers:
            for c in row:
                tiers.extend(_tiers_from_cell(c))
        tiers = list(dict.fromkeys(tiers))
        primary_tier: str | None = tiers[0] if tiers else None
        out.append(
            {
                "label": label,
                "notes": notes,
                "tier": primary_tier,
                "tiers": tiers,
                "h2_title": h2_title,
                "h3_title": h3_title,
                "category": category,
                "search_blob": " ".join(
                    [h2_title, h3_title or "", label, notes, tier_cell, " ".join(row)]
                ).lower(),
            }
        )
    return out


def parse_feature_inventory_markdown(content: str) -> dict[str, Any]:
    lines = content.splitlines()
    segments: list[dict[str, Any]] = []
    preamble: list[str] = []

    h2_title = ""
    h3_title: str | None = None
    category = "preamble"
    i = 0

    while i < len(lines):
        line = lines[i]
        raw = line.rstrip()

        if raw.startswith("# ") and not raw.startswith("##"):
            segments.append({"kind": "h1", "title": raw[2:].strip()})
            i += 1
            continue

        m2 = _H2.match(raw)
        if m2:
            h2_title = m2.group(1).strip()
            h3_title = None
            category = _category_from_h2_title(h2_title)
            segments.append(
                {
                    "kind": "h2",
                    "title": h2_title,
                    "id": _slug(h2_title),
                    "category": category,
                }
            )
            i += 1
            continue

        m3 = _H3.match(raw)
        if m3:
            h3_title = m3.group(1).strip()
            segments.append(
                {
                    "kind": "h3",
                    "title": h3_title,
                    "id": _slug(h3_title),
                    "category": category,
                }
            )
            i += 1
            continue

        if raw.strip() == "---":
            segments.append({"kind": "rule"})
            i += 1
            continue

        tbl, consumed = _parse_table(lines, i)
        if tbl and consumed:
            tbl["kind"] = "table"
            tbl["h2_title"] = h2_title
            tbl["h3_title"] = h3_title
            tbl["category"] = category
            segments.append(tbl)
            i += consumed
            continue

        if not h2_title and raw.strip():
            preamble.append(raw)
            i += 1
            continue

        if raw.strip():
            buf = [raw]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("#"):
                if lines[i].strip().startswith("|"):
                    break
                buf.append(lines[i].rstrip())
                i += 1
            segments.append(
                {
                    "kind": "paragraph",
                    "text": "\n".join(buf),
                    "h2_title": h2_title,
                    "h3_title": h3_title,
                    "category": category,
                }
            )
            continue

        i += 1

    flat_rows: list[dict[str, Any]] = []
    for seg in segments:
        if seg.get("kind") == "table" and "headers" in seg:
            flat_rows.extend(
                _table_to_flat_rows(
                    seg,
                    h2_title=seg.get("h2_title", ""),
                    h3_title=seg.get("h3_title"),
                    category=seg.get("category", "other"),
                )
            )

    categories = [{"id": k, "label": v} for k, v in _CATEGORY_LABELS.items() if k != "other"]
    categories.append({"id": "other", "label": "Other"})

    return {
        "segments": segments,
        "flat_rows": flat_rows,
        "categories": categories,
        "preamble": "\n".join(preamble).strip(),
    }


if __name__ == "__main__":
    import json
    import sys

    root = Path(__file__).resolve().parent.parent.parent.parent
    p = root / "FEATURE_INVENTORY.md"
    if not p.is_file():
        print("missing:", p, file=sys.stderr)
        sys.exit(1)
    out = parse_feature_inventory_markdown(p.read_text(encoding="utf-8"))
    print(json.dumps({"segments": len(out["segments"]), "flat_rows": len(out["flat_rows"])}))
