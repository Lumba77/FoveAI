"""
coder_tools.py — heavy-duty repo tooling for the coder persona and MCP layer.

Every write goes through edit_layers (the .foveignore layer gate + pre-edit
snapshots), so these tools are safe to expose to any model — local or cloud.
Pure synchronous functions returning plain dicts; no agent state.

Tools:
  repo_read_file / repo_list_dir / repo_search      — navigation
  repo_apply_patch / repo_write_file                — layered writes
  repo_blast_radius                                 — reverse-dependency scan
  repo_lint / repo_run_tests                        — verification rails
  repo_git_status / repo_git_diff                   — HUD working state
  todo_add / todo_list / todo_done                  — session todo HUD
  rollback_last_edit                                — revert the last applied edit
"""

import json
import logging
import os
import re
import subprocess
from typing import Any

from edit_layers import (
    FoveAI_ROOT,
    classify_edit_path,
    file_edit_proposal,
    rollback_edit,
    snapshot_before_edit,
)

logger = logging.getLogger(__name__)

TODO_PATH = os.path.join(FoveAI_ROOT, "Backend", "data", "coder_todos.json")
_MAX_READ = 40000
_MAX_LIST = 400


def _abs(path: str) -> str:
    return os.path.normpath(
        path if os.path.isabs(path) else os.path.join(FoveAI_ROOT, path)
    )


def _in_repo(path: str) -> bool:
    full = _abs(path)
    root = os.path.normpath(FoveAI_ROOT)
    return full == root or full.startswith(root + os.sep)


def _rel(path: str) -> str:
    return os.path.relpath(_abs(path), FoveAI_ROOT).replace("\\", "/")


# ── Navigation ────────────────────────────────────────────────────────────


def repo_read_file(path: str, start: int = 1, end: int = 0) -> dict[str, Any]:
    if classify_edit_path(path) == "FORBIDDEN":
        return {"error": "forbidden path"}
    full = _abs(path)
    if not _in_repo(full):
        return {"error": "outside repo"}
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return {"error": str(e)}
    s = max(1, int(start))
    e = int(end) if end else len(lines)
    chunk = "\n".join(f"{i + 1}: {lines[i]}" for i in range(s - 1, min(e, len(lines))))
    return {"file": _rel(path), "total_lines": len(lines), "content": chunk[:_MAX_READ]}


def repo_list_dir(path: str = ".") -> dict[str, Any]:
    full = _abs(path)
    if not _in_repo(full):
        return {"error": "outside repo"}
    try:
        entries = sorted(os.listdir(full))[:_MAX_LIST]
    except OSError as e:
        return {"error": str(e)}
    out = []
    for name in entries:
        d = os.path.join(full, name)
        out.append(name + ("/" if os.path.isdir(d) else ""))
    return {"dir": _rel(path) or ".", "entries": out}


# Code-bearing subtrees — repo-wide scans run against these only (the repo
# also holds multi-GB asset/model/build trees that grep can't crawl fast).
_SCAN_DIRS = [
    "Backend",
    "Tools",
    "Frontend",
    "jenna-vscode",
    "builder",
    "tests",
    "foveated-memory",
    "FoveAI_Console.py",
]
_EXCLUDE_DIRS = [
    ".git",
    ".venv",
    ".venv.bak",
    "venv",
    "node_modules",
    "__pycache__",
    "Library",
    "PackageCache",
    "Temp",
    "obj",
    "llama-b11053",
    "llama-bins",
    "Models",
    "dist",
    "build",
    ".cache",
    "xrl_encoded",
    "public/Animations",
]


def _scan_roots() -> list[str]:
    return [
        os.path.join(FoveAI_ROOT, d)
        for d in _SCAN_DIRS
        if os.path.exists(os.path.join(FoveAI_ROOT, d))
    ]


def _grep_base() -> list[str]:
    cmd = ["grep"]
    for d in _EXCLUDE_DIRS:
        cmd += [f"--exclude-dir={d}"]
    return cmd


def repo_search(
    pattern: str, glob: str = "", context: int = 2, limit: int = 40
) -> dict[str, Any]:
    cmd = _grep_base() + ["-rn", f"--context={int(context)}"]
    if glob:
        cmd.append(f"--include={glob}")
    cmd += ["-E", pattern] + _scan_roots()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        lines = [l for l in r.stdout.splitlines() if l][:limit]
        for i, l in enumerate(lines):
            if l.startswith(FoveAI_ROOT):
                lines[i] = l[len(FoveAI_ROOT) + 1 :]
        return {
            "pattern": pattern,
            "matches": lines,
            "truncated": len(r.stdout.splitlines()) > limit,
        }
    except Exception as e:
        return {"error": str(e)}


# ── Layered writes ────────────────────────────────────────────────────────


def repo_apply_patch(path: str, search: str, replacement: str) -> dict[str, Any]:
    """Search/replace a single hunk. Layered: FORBIDDEN blocked, PROTECTED →
    proposal, OPEN → snapshot + apply."""
    layer = classify_edit_path(path)
    if layer == "FORBIDDEN":
        return {"error": "forbidden layer (secrets/system)"}
    if layer == "PROTECTED":
        return file_edit_proposal(path, search, replacement)
    full = _abs(path)
    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return {"error": str(e)}
    if search not in content:
        return {"error": "search text not found verbatim"}
    edit_id = snapshot_before_edit(full, actor="coder")
    with open(full, "w", encoding="utf-8") as f:
        f.write(content.replace(search, replacement, 1))
    return {"applied": True, "file": _rel(path), "edit_id": edit_id}


def repo_write_file(path: str, content: str) -> dict[str, Any]:
    """Create or overwrite a whole file. Layered like repo_apply_patch."""
    layer = classify_edit_path(path)
    if layer == "FORBIDDEN":
        return {"error": "forbidden layer (secrets/system)"}
    if layer == "PROTECTED":
        return file_edit_proposal(path, "<full file write>", content[:2000])
    full = _abs(path)
    edit_id = (
        snapshot_before_edit(full, actor="coder") if os.path.exists(full) else None
    )
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return {"error": str(e)}
    return {"written": True, "file": _rel(path), "edit_id": edit_id}


def rollback_last_edit(edit_id: str | None = None) -> dict[str, Any]:
    return rollback_edit(edit_id)


# ── HUD rails: blast radius, lint, tests, git ─────────────────────────────


def repo_blast_radius(path: str, limit: int = 30) -> dict[str, Any]:
    """Who references/imports this file? Maps path → module name and greps
    imports + bare-stem references. The coder checks this BEFORE editing."""
    rel = _rel(path)
    stem = os.path.splitext(os.path.basename(rel))[0]
    dotted = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
    hits = {"imports": [], "references": []}
    try:
        for pat, bucket in (
            (rf"(from|import)\s+[\w.]*{re.escape(stem)}", "imports"),
            (re.escape(stem), "references"),
        ):
            r = subprocess.run(
                _grep_base()
                + [
                    "-rln",
                    "-E",
                    pat,
                    "--include=*.py",
                    "--include=*.js",
                    "--include=*.ts",
                ]
                + _scan_roots(),
                capture_output=True,
                text=True,
                timeout=30,
            )
            files = [
                l[len(FoveAI_ROOT) + 1 :]
                for l in r.stdout.splitlines()
                if l.startswith(FoveAI_ROOT) and _rel(l) != rel
            ][:limit]
            hits[bucket] = files
    except Exception as e:
        return {"error": str(e)}
    return {
        "file": rel,
        "module": dotted,
        **hits,
        "note": "files importing/referencing this — changes ripple here",
    }


def repo_lint(path: str) -> dict[str, Any]:
    """py_compile (+ pyflakes if installed) on a Python file."""
    full = _abs(path)
    if not full.endswith(".py"):
        return {"skipped": "not a python file"}
    r = subprocess.run(
        ["python3", "-m", "py_compile", full],
        capture_output=True,
        text=True,
        timeout=30,
    )
    issues = (r.stderr or "").strip()
    try:
        r2 = subprocess.run(
            ["python3", "-m", "pyflakes", full],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r2.stdout.strip():
            issues += ("\n" if issues else "") + r2.stdout.strip()
    except Exception:
        pass
    return {"file": _rel(path), "ok": not issues, "issues": issues or "clean"}


def repo_run_tests(path: str = "tests", timeout: int = 120) -> dict[str, Any]:
    """Run pytest on a file/dir under the repo (bounded)."""
    full = _abs(path)
    if not _in_repo(full):
        return {"error": "outside repo"}
    venv_py = os.path.join(FoveAI_ROOT, ".venv", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else "python3"
    try:
        r = subprocess.run(
            [py, "-m", "pytest", full, "-x", "-q"],
            capture_output=True,
            text=True,
            timeout=min(int(timeout), 300),
            cwd=FoveAI_ROOT,
        )
        tail = "\n".join((r.stdout + r.stderr).splitlines()[-30:])
        return {"returncode": r.returncode, "output": tail}
    except subprocess.TimeoutExpired:
        return {"error": f"tests timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def repo_git_status() -> dict[str, Any]:
    r = subprocess.run(
        ["git", "status", "--short"],
        cwd=FoveAI_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = r.stdout.splitlines()[:100]
    return {"changed": len(lines), "files": lines}


def repo_git_diff(path: str = "") -> dict[str, Any]:
    cmd = ["git", "diff", "--"] + ([_rel(path)] if path else [])
    r = subprocess.run(cmd, cwd=FoveAI_ROOT, capture_output=True, text=True, timeout=20)
    return {"diff": r.stdout[:_MAX_READ] or "(clean)"}


# ── Todo HUD ──────────────────────────────────────────────────────────────
# Todos live in agent_plans (persistent_memory) — the same substrate as Jen's
# tasks (<self:todo>) — so coder models, the autonomous loop, and the Multigate
# UI all see one shared todo list. A persistent [CODER] plan carries the steps;
# the legacy coder_todos.json is migrated into it once, then ignored.


def _coder_plan_id() -> int:
    """The shared [CODER] session plan — single todo substrate for all models."""
    from persistent_memory import create_plan, get_memory, get_plan, set_memory

    raw = get_memory("coder_session_plan_id")
    if raw:
        try:
            plan = get_plan(int(raw))
            if plan and plan.get("status") not in ("abandoned",):
                return int(raw)
        except (ValueError, TypeError):
            pass
    pid = create_plan(
        title="[CODER] session todos",
        description="Shared todo substrate — coder models' todo_add/todo_done are steps here",
        origin="coder",
    )
    set_memory("coder_session_plan_id", str(pid))
    # one-time migration of the legacy JSON todo list
    try:
        with open(TODO_PATH, encoding="utf-8") as f:
            for t in json.load(f):
                step = f"[✓] {t['task']}" if t.get("done") else t["task"]
                add_plan_step(pid, step)
    except Exception:
        pass
    return pid


def _load_todos() -> list[dict[str, Any]]:
    """Steps on the [CODER] plan rendered as todo dicts (1-indexed ids)."""
    from persistent_memory import get_plan

    plan = get_plan(_coder_plan_id())
    steps = (plan or {}).get("steps", [])
    out = []
    for i, s in enumerate(steps):
        done = s.startswith("[✓]")
        out.append({"id": i + 1, "task": s[3:].strip() if done else s, "done": done})
    return out


def todo_add(task: str) -> dict[str, Any]:
    from persistent_memory import add_plan_step, get_plan

    pid = _coder_plan_id()
    add_plan_step(pid, task)
    n = len((get_plan(pid) or {}).get("steps", []))
    return {"added": {"id": n, "task": task, "done": False}, "plan_id": pid}


def todo_list() -> dict[str, Any]:
    return {"todos": _load_todos()}


def todo_done(todo_id: int) -> dict[str, Any]:
    from persistent_memory import complete_plan_step

    pid = _coder_plan_id()
    todos = _load_todos()
    for t in todos:
        if t["id"] == int(todo_id):
            complete_plan_step(pid, int(todo_id) - 1)
            t["done"] = True
            return {"completed": t}
    return {"error": f"no todo #{todo_id}"}


# ── OpenAI-compatible tool schemas (for the coder agentic loop) ───────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "repo_read_file",
            "description": "Read a repo file (numbered lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_list_dir",
            "description": "List a repo directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_search",
            "description": "Regex search across the repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "glob": {"type": "string"},
                    "context": {"type": "integer"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_apply_patch",
            "description": "Apply a search/replacement hunk to a file (layered + snapshotted).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "search": {"type": "string"},
                    "replacement": {"type": "string"},
                },
                "required": ["path", "search", "replacement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_write_file",
            "description": "Create/overwrite a whole file (layered + snapshotted).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_blast_radius",
            "description": "Find what imports/references a file before editing it.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_lint",
            "description": "Compile/lint check a Python file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_run_tests",
            "description": "Run pytest on a path (bounded).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_git_status",
            "description": "Show changed files.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_git_diff",
            "description": "Show working diff.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_add",
            "description": "Add a task to the session todo HUD.",
            "parameters": {
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_list",
            "description": "Show the session todo HUD.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_done",
            "description": "Mark a todo complete.",
            "parameters": {
                "type": "object",
                "properties": {"todo_id": {"type": "integer"}},
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_last_edit",
            "description": "Revert the most recent applied edit.",
            "parameters": {
                "type": "object",
                "properties": {"edit_id": {"type": "string"}},
            },
        },
    },
]

TOOL_FUNCS = {
    "repo_read_file": repo_read_file,
    "repo_list_dir": repo_list_dir,
    "repo_search": repo_search,
    "repo_apply_patch": repo_apply_patch,
    "repo_write_file": repo_write_file,
    "repo_blast_radius": repo_blast_radius,
    "repo_lint": repo_lint,
    "repo_run_tests": repo_run_tests,
    "repo_git_status": repo_git_status,
    "repo_git_diff": repo_git_diff,
    "todo_add": todo_add,
    "todo_list": todo_list,
    "todo_done": todo_done,
    "rollback_last_edit": rollback_last_edit,
}


# ── HUD context — ambient rails injected into every model's prompt ────────


def hud_context() -> str:
    """Render the self-development HUD as a compact prompt block: open todos,
    recent self-edits, pending proposals, working-tree state, coder status.
    Cheap — single fast git call, journal reads only."""
    from edit_layers import PROPOSALS_PATH, SELF_EDITS_JOURNAL

    parts = ["[HUD — self-development state]"]

    # Open todos across ALL active task plans — Jen's <self:todo> items and
    # coder todo_add steps share agent_plans, so every model sees one list.
    try:
        from persistent_memory import get_active_plans

        open_items = []
        for p in get_active_plans():
            if not p.get("title", "").startswith(("[TASK]", "[CODER]")):
                continue
            for i, s in enumerate(p.get("steps", [])):
                if not s.startswith("[✓]"):
                    open_items.append(f"p{p['id']}.{i + 1} {s}")
        if open_items:
            parts.append("Todos: " + "; ".join(open_items[:10]))
    except Exception:
        open_todos = [t for t in _load_todos() if not t.get("done")]
        if open_todos:
            parts.append(
                "Todos: " + "; ".join(f"#{t['id']} {t['task']}" for t in open_todos[:8])
            )

    try:
        with open(SELF_EDITS_JOURNAL, encoding="utf-8") as f:
            entries = [json.loads(l) for l in f if l.strip()][-5:]
        if entries:
            parts.append(
                "Recent self-edits: "
                + ", ".join(
                    f"{e['file']}({e['id'].split('_')[0][-6:]})" for e in entries
                )
            )
    except Exception:
        pass

    try:
        n = sum(1 for _ in open(PROPOSALS_PATH, encoding="utf-8"))
        if n:
            parts.append(f"Pending proposals: {n} awaiting architect review")
    except Exception:
        pass

    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=FoveAI_ROOT,
            capture_output=True,
            text=True,
            timeout=8,
        )
        dirty = len(r.stdout.splitlines())
        parts.append(f"Working tree: {dirty} changed files")
    except Exception:
        pass

    coder = (
        "configured" if os.environ.get("FOVEAI_CODER_BASE_URL") else "not configured"
    )
    parts.append(f"Coder persona: {coder}")
    return "\n".join(parts)
