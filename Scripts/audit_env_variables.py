#!/usr/bin/env python3
"""
Repo-wide FoveAI_ environment variable audit.

Scans source files for:
- os.getenv("FoveAI_*", default)  [Python]
- process.env.FoveAI_* / process.env["FoveAI_*"] [JS/TS]
- set_key(..., "FoveAI_*", ...)   [Python dotenv writes]
- Any literal "FoveAI_" string assignment in JS/TS/HTML that looks like a write
- References in .env file itself

Outputs:
- .logs/env_audit_report.json   (structured data)
- .logs/env_audit_report.md     (human-readable summary)
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / ".logs"
OUT_JSON = OUT_DIR / "env_audit_report.json"
OUT_MD = OUT_DIR / "env_audit_report.md"

# Directories to skip entirely
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "out",
    "coverage",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "Archive",
    "Training",
    ".backup_fixes",
    ".backups",
    ".SafeSave",
    ".SafeSaves",
    "memory_data",
    "checkpoints",
    "memory.db",
    ".logs",
}

# File extensions to scan
SOURCE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".htm",
    ".vue",
    ".svelte",
    ".ps1",
    ".sh",
    ".bash",
    ".yaml",
    ".yml",
    ".json",
}

# Regex patterns
VAR_NAME_RE = re.compile(r"FoveAI_[A-Z0-9_]+")
PY_GET_RE = re.compile(
    r'os\.(?:environ\.get|getenv)\s*\(\s*["\'](FoveAI_[A-Z0-9_]+)["\']'
)
PY_SET_KEY_RE = re.compile(
    r'(?:dotenv\.)?set_key\s*\(\s*[^,]+,\s*["\'](FoveAI_[A-Z0-9_]+)["\']'
)
PY_LOAD_RE = re.compile(r"load_dotenv")
JS_GET_RE = re.compile(
    r'process\.env\.(FoveAI_[A-Z0-9_]+)|process\.env\(["\'](FoveAI_[A-Z0-9_]+)["\']\)'
)
# Only treat as a JS/TS/HTML write when the key appears in an object literal that is
# assigned to a variable named updates/envUpdates or passed to fetch/JSON.stringify.
JS_OBJ_KEY_RE = re.compile(
    r'(?:const|let|var)\s+(?:updates|envUpdates|env)\s*=\s*\{[^}]*?["\'](FoveAI_[A-Z0-9_]+)["\']\s*:\s*([^,\n}]+)'
    r'|JSON\.stringify\s*\(\s*\{[^}]*?["\'](FoveAI_[A-Z0-9_]+)["\']\s*:\s*([^,\n}]+)'
)
ENV_LINE_RE = re.compile(r"^\s*(FoveAI_[A-Z0-9_]+)\s*=\s*(.*?)\s*$")


def should_skip_dir(path: Path) -> bool:
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def scan_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    findings = []
    is_json = path.suffix.lower() == ".json"

    # Python reads
    for m in PY_GET_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        default = extract_default(text, m.end())
        findings.append(
            {
                "type": "read",
                "var": m.group(1),
                "line": line,
                "default": default,
                "lang": "python",
            }
        )

    # Python dotenv writes
    for m in PY_SET_KEY_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        findings.append(
            {"type": "write", "var": m.group(1), "line": line, "lang": "python"}
        )

    # JS/TS reads
    for m in JS_GET_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        var = m.group(1) or m.group(2)
        findings.append(
            {"type": "read", "var": var, "line": line, "lang": "javascript"}
        )

    # JS/TS/HTML object literal writes like {"FoveAI_X": "value"}
    # Skip JSON config files — those are not runtime writes
    if not is_json:
        for m in JS_OBJ_KEY_RE.finditer(text):
            line = text[: m.start()].count("\n") + 1
            var = m.group(1) or m.group(3)
            value = m.group(2) or m.group(4)
            findings.append(
                {
                    "type": "write",
                    "var": var,
                    "line": line,
                    "value_expr": value.strip(),
                    "lang": "javascript",
                }
            )

    # Generic fallback: any FoveAI_ variable name in source
    for m in VAR_NAME_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        var = m.group(0)
        # Skip if already captured
        if not any(f["var"] == var and f["line"] == line for f in findings):
            findings.append(
                {
                    "type": "mention",
                    "var": var,
                    "line": line,
                    "lang": path.suffix.lstrip("."),
                }
            )

    return rel, findings


def extract_default(text: str, end_pos: int) -> str:
    """Try to pull the default value from os.getenv(..., default)."""
    rest = text[end_pos:].lstrip()
    if rest.startswith(","):
        rest = rest[1:].lstrip()
        if rest.startswith('"'):
            m = re.match(r'"([^"]*)"', rest)
            return m.group(1) if m else None
        if rest.startswith("'"):
            m = re.match(r"'([^']*)'", rest)
            return m.group(1) if m else None
    return None


def scan_dotenv(path: Path = REPO_ROOT / ".env"):
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    findings = []
    if not path.exists():
        return rel, findings
    for i, line in enumerate(
        path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
    ):
        m = ENV_LINE_RE.match(line)
        if m:
            findings.append(
                {"type": "env_file", "var": m.group(1), "line": i, "value": m.group(2)}
            )
    return rel, findings


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_files = {}
    for root, dirs, files in os.walk(REPO_ROOT):
        root_path = Path(root)
        if should_skip_dir(root_path):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for f in files:
            fp = root_path / f
            if fp.suffix.lower() in SOURCE_EXTS:
                if should_skip_dir(fp.parent):
                    continue
                rel, findings = scan_file(fp)
                if findings:
                    all_files[rel] = findings

    env_rel, env_findings = scan_dotenv()
    if env_findings:
        all_files[env_rel] = env_findings

    # Aggregate by variable
    by_var = defaultdict(
        lambda: {"reads": [], "writes": [], "mentions": [], "env_values": []}
    )
    for rel, findings in all_files.items():
        for f in findings:
            var = f["var"]
            entry = {"file": rel, "line": f.get("line")}
            if f["type"] == "read":
                entry["default"] = f.get("default")
                entry["lang"] = f.get("lang")
                by_var[var]["reads"].append(entry)
            elif f["type"] == "write":
                entry["value_expr"] = f.get("value_expr")
                entry["lang"] = f.get("lang")
                by_var[var]["writes"].append(entry)
            elif f["type"] == "mention":
                entry["lang"] = f.get("lang")
                by_var[var]["mentions"].append(entry)
            elif f["type"] == "env_file":
                entry["value"] = f.get("value")
                by_var[var]["env_values"].append(entry)

    # Detect issues
    issues = []
    for var, data in by_var.items():
        if len(data["writes"]) > 1:
            issues.append(
                {
                    "kind": "multiple_writers",
                    "var": var,
                    "count": len(data["writes"]),
                    "writers": data["writes"],
                }
            )
        if data["writes"] and not data["env_values"]:
            issues.append(
                {"kind": "write_but_not_in_env", "var": var, "writers": data["writes"]}
            )
        if data["reads"] and not data["env_values"] and not data["writes"]:
            issues.append(
                {"kind": "read_but_never_set", "var": var, "reads": data["reads"]}
            )

    # Detect same default value used by different vars
    default_map = defaultdict(list)
    for var, data in by_var.items():
        for r in data["reads"]:
            if r.get("default"):
                default_map[r["default"]].append(
                    {"var": var, "file": r["file"], "line": r["line"]}
                )
    for default, vars_info in default_map.items():
        if len({v["var"] for v in vars_info}) > 1:
            issues.append(
                {"kind": "shared_default_value", "value": default, "vars": vars_info}
            )

    report = {
        "summary": {
            "files_scanned": len(all_files),
            "variables_found": len(by_var),
            "issues_found": len(issues),
        },
        "variables": dict(by_var),
        "issues": issues,
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Markdown report
    md = []
    md.append("# FoveAI Environment Variable Audit\n")
    md.append(f"Files scanned: {report['summary']['files_scanned']}  \n")
    md.append(f"Variables found: {report['summary']['variables_found']}  \n")
    md.append(f"Issues found: {report['summary']['issues_found']}  \n")
    md.append("\n## Issues\n")
    if not issues:
        md.append("No issues detected.\n")
    for issue in issues:
        md.append(
            f"\n### {issue['kind']}: `{issue['var'] if 'var' in issue else issue.get('value')}`\n"
        )
        if issue["kind"] == "multiple_writers":
            md.append(f"Written by {issue['count']} different places:\n")
            for w in issue["writers"]:
                md.append(
                    f"- [`{w['file']}:{w['line']}`]({w['file']}:{w['line']}) value=`{w.get('value_expr', 'N/A')}`\n"
                )
        elif issue["kind"] == "write_but_not_in_env":
            md.append("Code writes this variable but it is not present in `.env`:\n")
            for w in issue["writers"]:
                md.append(f"- [`{w['file']}:{w['line']}`]({w['file']}:{w['line']})\n")
        elif issue["kind"] == "read_but_never_set":
            md.append("Read in code but never written or present in `.env`:\n")
            for r in issue["reads"]:
                md.append(f"- [`{r['file']}:{r['line']}`]({r['file']}:{r['line']})\n")
        elif issue["kind"] == "shared_default_value":
            md.append(
                f"Same default value `{issue['value']}` used by multiple variables:\n"
            )
            for v in issue["vars"]:
                md.append(
                    f"- `{v['var']}` at [`{v['file']}:{v['line']}`]({v['file']}:{v['line']})\n"
                )

    md.append("\n## All Variables\n")
    for var in sorted(by_var.keys()):
        data = by_var[var]
        md.append(f"\n### `{var}`\n")
        if data["env_values"]:
            md.append(f"**.env value:** `{data['env_values'][0]['value']}`\n")
        if data["reads"]:
            md.append("**Reads:**\n")
            for r in data["reads"]:
                default = f" (default: `{r['default']}`)" if r.get("default") else ""
                md.append(
                    f"- [`{r['file']}:{r['line']}`]({r['file']}:{r['line']}){default}\n"
                )
        if data["writes"]:
            md.append("**Writes:**\n")
            for w in data["writes"]:
                md.append(
                    f"- [`{w['file']}:{w['line']}`]({w['file']}:{w['line']}) value=`{w.get('value_expr', 'N/A')}`\n"
                )
        if data["mentions"]:
            md.append("**Mentions:**\n")
            for m in data["mentions"]:
                md.append(f"- [`{m['file']}:{m['line']}`]({m['file']}:{m['line']})\n")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
