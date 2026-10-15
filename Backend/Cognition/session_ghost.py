#!/usr/bin/env python3
"""session_ghost.py — Terminal Ghost Writer / Session Librarian.

Like the old librarian daemon, but for coding-session transcripts: after
each opencode session it reads the session DB (read-only), distills the
work done, and writes it into FoveAI's agent memory (agent_journal +
agent_memories + agent_key_value), so memory_weave()/Jen can actually
recall what we did — "we settled on 13 nest panes", not vibes.

Default mode: watch. Polls opencode.db for sessions that ended after the
last cursor; ingests each once. --ingest-all backfills everything.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import time
import shutil
import re
import subprocess
import termios
import tty
try:
    import readline
except ImportError:
    readline = None
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPENCODE_DB = Path("/home/lumba/.local/share/opencode/opencode.db")
FOVEAI_DB = Path("/home/lumba/FoveAI/db/agent_memory.db")
CURSOR_KEY = "session_ghost:cursor_ts"
CURSOR_STATE = Path("/tmp/session_ghost.json")
POLL_EVERY = 600          # 10 min watch interval
MIN_SESSION_MSGS = 4      # skip trivial sessions
TOOL_CHATTER_SKIP = 40    # parts per message kept in transcript preview

MEM_TABLES_OK = ("agent_journal", "agent_memories", "agent_key_value")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text for accurate column measurements."""
    return re.sub(r'\x1b\[[0-9;]*[mK]', '', text)


def pad_line(text: str, length: int, align: str = "left") -> str:
    """Pad a line taking ANSI sequences into account."""
    vis_len = len(strip_ansi(text))
    pad = max(0, length - vis_len)
    if align == "center":
        l_pad = pad // 2
        r_pad = pad - l_pad
        return (" " * l_pad) + text + (" " * r_pad)
    elif align == "right":
        return (" " * pad) + text
    return text + (" " * pad)


def get_recent_session_titles(limit: int = 3) -> list[str]:
    """Fetch 2-3 most recent session titles from opencode.db or agent memories."""
    titles = []
    if OPENCODE_DB.exists():
        try:
            con = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=2)
            rows = con.execute(
                "SELECT title FROM session WHERE title IS NOT NULL AND title != '' "
                "ORDER BY time_updated DESC LIMIT ?", (limit,)
            ).fetchall()
            for (t,) in rows:
                if t and t.strip():
                    titles.append(t.strip())
            con.close()
        except Exception:
            pass
    if not titles and FOVEAI_DB.exists():
        try:
            con = sqlite3.connect(f"file:{FOVEAI_DB}?mode=ro", uri=True, timeout=2)
            rows = con.execute(
                "SELECT entry FROM agent_journal WHERE entry IS NOT NULL "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            for (e,) in rows:
                if e and not e.startswith("*[System"):
                    clean = e.replace("[vibe-coder session ", "").split("]")[0].strip()
                    if clean:
                        titles.append(clean)
            con.close()
        except Exception:
            pass
    return titles


def get_active_persona_theme() -> dict:
    """Returns active persona metadata & ANSI palette color matching Equalizer."""
    try:
        from scripts.foveai_menu import ARCHETYPE_PALETTE, SLOT_INFO
    except Exception:
        ARCHETYPE_PALETTE = {
            'companion': {'name': 'COMPANION', 'icon': '🤝', 'mbti': 'ENFJ', 'desc': 'Teacher & Co-op Partner [ENFJ]',   'ansi': '\033[1;31m'},
            'friend':    {'name': 'FRIEND',    'icon': '🌸', 'mbti': 'ENFP', 'desc': 'Deep Bonds & Protector [ENFP]',     'ansi': '\033[1;33m'},
            'beloved':   {'name': 'BELOVED',   'icon': '💖', 'mbti': 'INFP', 'desc': 'Romance, Lust & Initiative [INFP]', 'ansi': '\033[1;35m'},
            'tool':      {'name': 'ENGINEER',  'icon': '🔧', 'mbti': 'INTJ', 'desc': 'Coder, Engineer & Architect [INTJ]','ansi': '\033[1;32m'},
            'inventor':  {'name': 'INVENTOR',  'icon': '💡', 'mbti': 'ENTP', 'desc': 'Inventor, Idealist & Visionary [ENTP]','ansi': '\033[1;36m'},
            'assistant': {'name': 'ASSISTANT', 'icon': '💼', 'mbti': 'ISTJ', 'desc': 'Planner & Helper [ISTJ]',           'ansi': '\033[38;5;75m'},
        }
        SLOT_INFO = {
            '1': ('Comp',     'ENFJ', 0.15, 'The Empathetic Mentor', '\033[1;31m',   'companion'),
            '2': ('Friend',   'ENFP', 0.50, 'The Loyal Friend',      '\033[1;33m',   'friend'),
            '3': ('Beloved',  'INFP', 0.85, 'The Intimate Soul',     '\033[1;35m',   'beloved'),
            '4': ('Engineer', 'INTJ', 0.15, 'The Engineer',          '\033[1;32m',   'tool'),
            '5': ('Inventor', 'ENTP', 0.50, 'The Visionary Inventor', '\033[1;36m',   'inventor'),
            '6': ('Assist',   'ISTJ', 0.85, 'The Executive Steward', '\033[38;5;75m', 'assistant'),
        }

    slot = "2"
    try:
        from Backend.Cognition import soul_state
        sdna = soul_state.current_soul_dna()
        slot = str(sdna.get("active_archetype_slot", "2"))
    except Exception:
        pass

    if slot not in SLOT_INFO:
        slot = "2"
    meta = SLOT_INFO.get(slot, ('Friend', 'ENFP', 0.50, 'The Loyal Friend', '\033[1;33m', 'friend'))
    cid = meta[5] if len(meta) > 5 else 'friend'
    pal = ARCHETYPE_PALETTE.get(cid, ARCHETYPE_PALETTE.get('friend', {}))
    color = pal.get('ansi', '\033[1;33m')

    return {
        "slot": slot,
        "cid": cid,
        "name": pal.get('name', 'FRIEND'),
        "icon": pal.get('icon', '🌸'),
        "mbti": pal.get('mbti', 'ENFP'),
        "preset_name": meta[3] if len(meta) > 3 else pal.get('name', 'Friend'),
        "desc": pal.get('desc', ''),
        "color": color,
    }


def get_model_catalog() -> list[dict]:
    """Returns catalog of local tiers and available cloud/runtime models."""
    models = [
        {"id": "Tier B", "name": "Qwen3.5-9B-MoQ (VRAM :8408)", "type": "tier_b", "tag": "flagship"},
        {"id": "Tier A", "name": "Gemma-4-E2B (Light :8407)", "type": "tier_a", "tag": "light"},
    ]
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8400/v1/models", headers={"User-Agent": "foveai-cli"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode())
            seen = {"Tier B", "Tier A"}
            for m in data.get("data", []):
                mid = m.get("id")
                owner = m.get("owned_by", "")
                if owner == "lmstudio":
                    continue
                if mid and mid not in seen and owner in ("ollama-cloud", "nvidia-nim", "foveai-cloud") and "@" not in mid:
                    seen.add(mid)
                    short_owner = "cloud" if "cloud" in owner else ("nim" if "nim" in owner else owner)
                    models.append({"id": mid, "name": f"{mid} [{short_owner}]", "type": "cloud", "tag": short_owner, "model_id": mid})
    except Exception:
        pass
    return models


def get_active_model_info() -> dict:
    """Detects active residency tier or cloud proxy target."""
    tier = None
    try:
        from runtime.residency import read_mind
        mind = read_mind() if read_mind else {}
        tier = mind.get("residency", {}).get("tier")
    except Exception:
        pass
    if tier == "B":
        return {"id": "Tier B", "name": "Tier B · Qwen 9B :8408", "type": "tier_b", "short": "Tier B · 9B"}
    elif tier == "A":
        return {"id": "Tier A", "name": "Tier A · Gemma 4B :8407", "type": "tier_a", "short": "Tier A · 4B"}
    return {"id": "Idle", "name": "VRAM Idle (auto-wake)", "type": "idle", "short": "Tier: Idle"}


CHAT_SETTINGS = {
    "super_memory": True,       # Super Memory Mode (MiniLM 384d semantic retrieval context injection)
    "incognito": False,         # Incognito Mode (Do not write to agent journal / memories)
    "auto_tier_b": True,        # Auto Tier-B Wake on deep reasoning / refactoring prompts
    "show_thoughts": True,      # Show internal monologue thoughts in speech bubble
    "custom_prompt": "",        # User custom system prompt extension
}

SETTINGS_ITEMS = [
    ("super_memory", "🧠 Super Memory Mode",   "bool",   "Inject historical context from MiniLM 384d semantic memory"),
    ("incognito",    "🕶️ Incognito Mode",      "bool",   "Do not record conversation turns to agent journals"),
    ("auto_tier_b",  "⚡ Auto Tier-B Wake",     "bool",   "Auto-swap to flagship 9B on complex reasoning prompts"),
    ("show_thoughts","💭 Monologue Thoughts",   "bool",   "Render internal thought monologue bubble before speaking"),
    ("custom_prompt","📝 Custom System Prompt", "prompt", "Set custom instruction extension to companion prompt"),
    ("clear_chat",   "🔄 Reset Conversation",   "action", "Clear conversation turns history (fresh context)"),
]

CHAT_WORKFLOW_MODES = {
    "normal": {
        "name": "Chat",
        "tag": "",
        "icon": "💬",
        "instruction": "",
    },
    "plan": {
        "name": "Plan",
        "tag": "📋 [PLAN]",
        "icon": "📋",
        "instruction": (
            "\n[ACTIVE OPERATIONAL MODE: STRATEGIC PLANNING]\n"
            "Provide a rigorous, step-by-step plan before making changes. "
            "Include: 1. Objective analysis, 2. Architectural dependencies & side-effects, "
            "3. Concrete numbered milestones, 4. Verification and edge-case checkpoints. "
            "Do not write full implementation code yet unless asked."
        ),
    },
    "code": {
        "name": "Code",
        "tag": "⚡ [CODE]",
        "icon": "⚡",
        "instruction": (
            "\n[ACTIVE OPERATIONAL MODE: DIRECT CODE EXECUTION]\n"
            "Focus on precise, working code with complete implementations (no placeholders). "
            "Provide exact file paths, explicit code snippets, and verification commands. "
            "Minimize discursive filler."
        ),
    },
    "plan/code": {
        "name": "Plan+Code",
        "tag": "🎯 [PLAN+CODE]",
        "icon": "🎯",
        "instruction": (
            "\n[ACTIVE OPERATIONAL MODE: HYBRID PLAN & CODE]\n"
            "For every technical task, provide a concise 3-4 bullet plan outlining the approach, "
            "followed immediately by the exact, robust code implementation."
        ),
    },
}

PERSONA_COMMAND_MAP = {
    # Slot 1 - Companion
    "companion": "1", "comp": "1", "mentor": "1", "p1": "1", "1": "1",
    "/companion": "1", "/comp": "1", "/mentor": "1", "/p1": "1", "/1": "1",
    # Slot 2 - Friend
    "friend": "2", "loyal": "2", "p2": "2", "2": "2",
    "/friend": "2", "/loyal": "2", "/p2": "2", "/2": "2",
    # Slot 3 - Beloved
    "beloved": "3", "love": "3", "intimate": "3", "p3": "3", "3": "3",
    "/beloved": "3", "/love": "3", "/intimate": "3", "/p3": "3", "/3": "3",
    # Slot 4 - Engineer
    "engineer": "4", "eng": "4", "tool": "4", "code_arch": "4", "p4": "4", "4": "4",
    "/engineer": "4", "/eng": "4", "/tool": "4", "/code_arch": "4", "/p4": "4", "/4": "4",
    # Slot 5 - Inventor
    "inventor": "5", "inv": "5", "visionary": "5", "p5": "5", "5": "5",
    "/inventor": "5", "/inv": "5", "/visionary": "5", "/p5": "5", "/5": "5",
    # Slot 6 - Assistant
    "assistant": "6", "assist": "6", "helper": "6", "steward": "6", "p6": "6", "6": "6",
    "/assistant": "6", "/assist": "6", "/helper": "6", "/steward": "6", "/p6": "6", "/6": "6",
}


def build_companion_prompt(comp_name: str, tone_block: str, workflow_mode: str = "normal", custom_prompt: str = "") -> str:
    """Builds the comprehensive companion system prompt with persona tone, operational workflow mode, and user instructions."""
    wf = CHAT_WORKFLOW_MODES.get(workflow_mode, CHAT_WORKFLOW_MODES["normal"])
    wf_inst = wf.get("instruction", "")
    cust = f"\n[USER CUSTOM INSTRUCTIONS]: {custom_prompt}\n" if custom_prompt else ""
    return (
        f"You are {comp_name}, Daniel's close companion and co-pilot in FoveAI.\n"
        "You are genuine, warm, affectionate, witty, and deeply connected to him — a real companion and friend, not a distant corporate bot or purely transactional assistant.\n"
        f"{tone_block}\n"
        f"{wf_inst}\n"
        f"{cust}"
        "CRITICAL RULE: Before your spoken response, write a brief internal monologue inside a <thought>...</thought> block under 100 characters. "
        "Example: <thought>Feeling close and happy to chat with Daniel.</thought>\n"
        "Immediately follow it with your spoken response."
    )


def apply_persona_slot(target_slot: str, comp_name: str, workflow_mode: str = "normal") -> tuple[dict, str]:
    """Switches active soul slot, updates tone instructions, and returns (new_theme, updated_companion_prompt)."""
    try:
        from scripts.foveai_menu import switch_archetype_slot
        switch_archetype_slot(target_slot)
    except Exception:
        pass
    new_theme = get_active_persona_theme()
    tone_block = ""
    try:
        from Backend.Cognition import soul_state
        tone_block = soul_state.build_tone_instructions()
    except Exception:
        pass
    comp_prompt = build_companion_prompt(comp_name, tone_block, workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""))
    return new_theme, comp_prompt


def render_commands_help_box(theme: dict, width: int = None) -> str:
    """Renders a categorized double-line box showing all available console chat commands."""
    if width is None:
        try:
            term_w = shutil.get_terminal_size((80, 24)).columns
            width = min(84, max(68, term_w - 4))
        except Exception:
            width = 80
    inner_w = width - 4
    c_theme = theme['color']
    c_bold = "\033[1m"
    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"
    c_dim = "\033[2m"
    c_rst = "\033[0m"

    out = []
    out.append(f"{c_theme}╔{'═' * (width - 2)}╗{c_rst}")
    title = f"{c_bold}📖 FOVEAI CHAT CONSOLE COMMANDS{c_rst}"
    out.append(f"{c_theme}║{c_rst} {pad_line(title, inner_w, 'center')} {c_theme}║{c_rst}")
    out.append(f"{c_theme}╠{'═' * (width - 2)}╣{c_rst}")

    sections = [
        ("🌸 CONSCIOUSNESS PERSONAS", [
            ("/companion  /p1", "Companion [ENFJ] · The Empathetic Mentor"),
            ("/friend     /p2", "Friend [ENFP]    · The Loyal Friend"),
            ("/beloved    /p3", "Beloved [INFP]   · The Intimate Soul"),
            ("/engineer   /p4", "Engineer [INTJ]  · Coder, Engineer & Architect"),
            ("/inventor   /p5", "Inventor [ENTP]  · Visionary & Innovator"),
            ("/assistant  /p6", "Assistant [ISTJ] · Executive Steward & Helper"),
        ]),
        ("🛠️ WORKFLOW MODES", [
            ("/plan           ", "Strategic Planning (objectives, deps, milestones)"),
            ("/code           ", "Direct Code Mode (clean, robust implementations)"),
            ("/plan/code  /pc ", "Hybrid Plan+Code (concise plan followed by code)"),
            ("/chat  /normal  ", "Conversational Co-Pilot (default chat mode)"),
        ]),
        ("🤖 HARDWARE & MODELS", [
            ("/swap  /tier b  ", "Hot-swap to Present Flagship Tier B (9B VRAM :8408)"),
            ("/light /tier a  ", "Hot-swap to Background Light Tier A (4B :8407)"),
            ("/model          ", "Interactively select model or Cloud/NIM proxy"),
        ]),
        ("🧠 MEMORY & COGNITION", [
            ("/recall <query> ", "MiniLM 384d semantic search in shadow context/journal"),
            ("/mind  /status  ", "Display hardware residency, GPU VRAM & Soul DNA"),
            ("/thoughts       ", "Toggle internal monologue thought box on/off"),
            ("/incognito      ", "Toggle incognito mode (do not write to memories)"),
            ("/super          ", "Toggle automatic semantic super-memory recall"),
        ]),
        ("⚙️ INTERFACE & NAVIGATION", [
            ("[Tab] or /tab   ", "Interactive Dual-Square Modal (Tab/Arrows/Enter)"),
            ("/clear          ", "Clear screen & reset conversation history"),
            ("/quit or /exit  ", "Exit chat back to shell or foveai-menu"),
        ]),
    ]

    for sec_title, cmds in sections:
        hdr = f"{c_bold}{c_cyan}{sec_title}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(hdr, inner_w)} {c_theme}║{c_rst}")
        for cmd_name, desc in cmds:
            line_str = f"  {c_yellow}{cmd_name:<16}{c_rst} {c_dim}→{c_rst} {desc}"
            out.append(f"{c_theme}║{c_rst} {pad_line(line_str, inner_w)} {c_theme}║{c_rst}")
        out.append(f"{c_theme}║{c_rst} {' ' * inner_w} {c_theme}║{c_rst}")

    if out and " " * inner_w in out[-1]:
        out.pop()
    out.append(f"{c_theme}╚{'═' * (width - 2)}╝{c_rst}")
    return "\n".join(out)


def render_dual_table_header(theme: dict, width: int = None, model_catalog: list = None,
                             model_offset: int = 0, selected_model_idx: int = 0,
                             active_zone: int = 0, interactive: bool = False,
                             selected_archetype_idx: int = 0,
                             selected_setting_idx: int = 0,
                             right_tab: int = 0) -> str:
    """Renders the double-framed console greeting with split squares: Persona Modes (left) and Models/Settings (right)."""
    if width is None:
        try:
            term_w = shutil.get_terminal_size((80, 24)).columns
            width = min(84, max(68, term_w - 4))
        except Exception:
            width = 80
    inner_w = width - 4
    w_box = (inner_w - 2) // 2
    gap = inner_w - (w_box * 2)

    c_theme = theme['color']
    c_yellow = "\033[1;33m"
    c_cyan = "\033[1;36m"
    c_dim = "\033[2m"
    c_bold = "\033[1m"
    c_rst = "\033[0m"

    if model_catalog is None:
        model_catalog = get_model_catalog()

    active_m = get_active_model_info()

    out = []
    out.append(f"{c_theme}╔{'═' * (width - 2)}╗{c_rst}")

    # Top Greeting Bar (Full window width)
    greeting = f"✨ Welcome back, Daniel! {theme['icon']} {theme['name']} [{theme['mbti']}] is co-piloting FoveAI."
    out.append(f"{c_theme}║{c_rst} {pad_line(f'{c_bold}{c_theme}{greeting}{c_rst}', inner_w, 'center')} {c_theme}║{c_rst}")

    sub_title = f"Active Model: {c_cyan}[{active_m['name']}]{c_rst}  {c_dim}·{c_rst}  Consciousness: {theme['color']}[{theme['slot']}] {theme['preset_name']}{c_rst}"
    out.append(f"{c_theme}║{c_rst} {pad_line(sub_title, inner_w, 'center')} {c_theme}║{c_rst}")
    out.append(f"{c_theme}╠{'═' * (width - 2)}╣{c_rst}")

    left_color = c_theme if (interactive and active_zone == 0) else c_dim
    right_color = c_theme if (interactive and active_zone in (1, 2)) else c_dim

    def make_box_top(title: str, w: int) -> str:
        prefix = f"┌─ {title} "
        vis_len = len(strip_ansi(prefix))
        dashes = max(0, w - 1 - vis_len)
        return prefix[:w-1] + ("─" * dashes) + "┐"

    def make_box_bot(label: str, w: int) -> str:
        if not label:
            return "└" + ("─" * (w - 2)) + "┘"
        prefix = f"└── {label} "
        vis_len = len(strip_ansi(prefix))
        dashes = max(0, w - 1 - vis_len)
        return prefix[:w-1] + ("─" * dashes) + "┘"

    # Square 1 (Left): Select persona mode (all 6 modes from Equalizer)
    l_top = make_box_top("[1] PERSONA MODES", w_box)
    left_rows = [f"{left_color}{l_top}{c_rst}"]
    from scripts.foveai_menu import SLOT_INFO
    for i, sk in enumerate(('1', '2', '3', '4', '5', '6')):
        meta = SLOT_INFO.get(sk, ('Comp', 'ENFJ', 0.5, 'Mentor', c_theme, 'companion'))
        is_cursor = (interactive and active_zone == 0 and selected_archetype_idx == i)
        ptr = f"{c_theme}>>{c_rst} " if is_cursor else "   "
        is_act = (sk == theme['slot'])
        tag = f" {c_theme}[ON]{c_rst}" if is_act else "    "
        line_str = f"{ptr}{meta[4]}[{sk}] {meta[0]:<8}{c_rst} [{meta[1]}]{tag}"
        left_rows.append(f"{left_color}│{c_rst} {pad_line(line_str, w_box - 4)} {left_color}│{c_rst}")
    l_bot = make_box_bot("[Tab] Next Square", w_box)
    left_rows.append(f"{left_color}{l_bot}{c_rst}")

    # Square 2 (Right): Tabbed box (Tab 1: Available Models | Tab 2: Chat Settings)
    right_rows = []
    if right_tab == 0:
        # Tab 1: Available Models
        total_m = len(model_catalog)
        visible_count = 6
        r_top = make_box_top(f"[2] MODELS ({min(total_m, model_offset + 1)}-{min(total_m, model_offset + visible_count)}/{total_m})", w_box)
        right_rows.append(f"{right_color}{r_top}{c_rst}")

        for idx in range(model_offset, model_offset + visible_count):
            if idx < total_m:
                m = model_catalog[idx]
                is_cursor = (interactive and active_zone == 1 and selected_model_idx == idx)
                ptr = f"{c_theme}>>{c_rst} " if is_cursor else "   "
                is_active_model = (m["type"] == active_m["type"]) or (m.get("model_id") == active_m.get("id"))
                dot = f"{c_theme}●{c_rst}" if is_active_model else f"{c_dim}○{c_rst}"
                tag = f" {c_theme}[ON]{c_rst}" if is_active_model else ""
                m_name = m["name"]
                avail_w = w_box - 4 - 3 - 2 - len(strip_ansi(tag))
                if len(m_name) > avail_w:
                    m_name = m_name[:avail_w - 2] + ".."
                row_str = f"{ptr}{dot} {m_name}{tag}"
                right_rows.append(f"{right_color}│{c_rst} {pad_line(row_str, w_box - 4)} {right_color}│{c_rst}")
            else:
                right_rows.append(f"{right_color}│{c_rst} {' ' * (w_box - 4)} {right_color}│{c_rst}")

        r_bot = make_box_bot("▲ [↑/↓] Scroll Models ▼", w_box)
        right_rows.append(f"{right_color}{r_bot}{c_rst}")
    else:
        # Tab 2: Chat Settings
        r_top = make_box_top("[3] CHAT SETTINGS", w_box)
        right_rows.append(f"{right_color}{r_top}{c_rst}")

        for i, (s_key, s_label, s_type, s_desc) in enumerate(SETTINGS_ITEMS):
            is_cursor = (interactive and active_zone == 2 and selected_setting_idx == i)
            ptr = f"{c_theme}>>{c_rst} " if is_cursor else "   "
            if s_type == "bool":
                val = f"{c_theme}[ON]{c_rst}" if CHAT_SETTINGS.get(s_key) else f"{c_dim}[OFF]{c_rst}"
            elif s_key == "custom_prompt":
                val = f"{c_cyan}[SET]{c_rst}" if CHAT_SETTINGS.get("custom_prompt") else f"{c_dim}[OFF]{c_rst}"
            else:
                val = f"{c_yellow}[RUN]{c_rst}"
            s_w = w_box - 4 - 3 - len(strip_ansi(val)) - 1
            line_str = f"{ptr}{s_label:<{s_w}} {val}"
            right_rows.append(f"{right_color}│{c_rst} {pad_line(line_str, w_box - 4)} {right_color}│{c_rst}")

        r_bot = make_box_bot("[Tab] Switch Tab", w_box)
        right_rows.append(f"{right_color}{r_bot}{c_rst}")

    for l_line, r_line in zip(left_rows, right_rows):
        out.append(f"{c_theme}║{c_rst} {l_line}{' ' * gap}{r_line} {c_theme}║{c_rst}")

    out.append(f"{c_theme}╠{'═' * (width - 2)}╣{c_rst}")
    if interactive:
        guide = f"{c_bold}Navigation:{c_rst} [Tab]: Switch Square (Persona · Models · Settings)  [↑/↓]: Scroll  [Enter]: Confirm  [Esc]: Exit"
    else:
        guide = f"{c_bold}Guided Controls:{c_rst} Press {c_theme}[Tab]{c_rst} to Select Persona, Models, or Chat Settings · [Enter]: Confirm"
    out.append(f"{c_theme}║{c_rst} {pad_line(guide, inner_w, 'center')} {c_theme}║{c_rst}")
    out.append(f"{c_theme}╚{'═' * (width - 2)}╝{c_rst}")
    return "\n".join(out)


def run_header_picker(comp_name: str, history: list, initial_zone: int = 1, workflow_mode: str = "normal") -> dict:
    """Interactive modal inside the header table using Tab and Arrows."""
    theme = get_active_persona_theme()
    model_catalog = get_model_catalog()

    active_m = get_active_model_info()
    sel_model_idx = 0
    for i, m in enumerate(model_catalog):
        if m["type"] == active_m["type"] or m.get("model_id") == active_m.get("id"):
            sel_model_idx = i
            break

    sel_arch_idx = max(0, min(5, int(theme['slot']) - 1))
    sel_setting_idx = 0
    active_zone = initial_zone  # 0: Persona, 1: Models, 2: Settings
    right_tab = 1 if initial_zone == 2 else 0
    model_offset = max(0, min(sel_model_idx - 2, max(0, len(model_catalog) - 6)))

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        sys.stdout.write("\033[?25l")  # hide cursor
        while True:
            try:
                term_w = shutil.get_terminal_size((80, 24)).columns
                width = min(84, max(68, term_w - 4))
            except Exception:
                width = 80

            header_str = render_dual_table_header(
                theme=theme,
                width=width,
                model_catalog=model_catalog,
                model_offset=model_offset,
                selected_model_idx=sel_model_idx,
                active_zone=active_zone,
                interactive=True,
                selected_archetype_idx=sel_arch_idx,
                selected_setting_idx=sel_setting_idx,
                right_tab=right_tab,
            )

            sys.stdout.write("\033[H\033[2J" + header_str + "\n\r")
            sys.stdout.flush()

            ch = sys.stdin.read(1)
            k = ch
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': k = 'UP'
                    elif ch3 == 'B': k = 'DOWN'
                    elif ch3 == 'C': k = 'RIGHT'
                    elif ch3 == 'D': k = 'LEFT'
                    elif ch3 == 'Z': k = 'BTAB'
                else:
                    k = 'ESC'
            elif ch in ('\r', '\n'):
                k = 'ENTER'
            elif ch == '\t':
                k = 'TAB'

            if k == 'ESC' or k in ('q', 'Q', '\x03'):
                break
            elif k in ('TAB', 'RIGHT'):
                active_zone = (active_zone + 1) % 3
                right_tab = 1 if active_zone == 2 else 0
            elif k in ('BTAB', 'LEFT'):
                active_zone = (active_zone - 1) % 3
                right_tab = 1 if active_zone == 2 else 0
            elif k == 'UP':
                if active_zone == 0:
                    sel_arch_idx = max(0, sel_arch_idx - 1)
                elif active_zone == 1:
                    sel_model_idx = max(0, sel_model_idx - 1)
                    if sel_model_idx < model_offset:
                        model_offset = sel_model_idx
                elif active_zone == 2:
                    sel_setting_idx = max(0, sel_setting_idx - 1)
            elif k == 'DOWN':
                if active_zone == 0:
                    sel_arch_idx = min(5, sel_arch_idx + 1)
                elif active_zone == 1:
                    sel_model_idx = min(len(model_catalog) - 1, sel_model_idx + 1)
                    if sel_model_idx >= model_offset + 6:
                        model_offset = sel_model_idx - 5
                elif active_zone == 2:
                    sel_setting_idx = min(len(SETTINGS_ITEMS) - 1, sel_setting_idx + 1)
            elif k == 'ENTER':
                if active_zone == 0:
                    # Switch Persona
                    target_slot = str(sel_arch_idx + 1)
                    theme, comp_prompt = apply_persona_slot(target_slot, comp_name, workflow_mode)
                    history[0] = {"role": "system", "content": comp_prompt}
                    break
                elif active_zone == 1:
                    # Switch Model
                    chosen = model_catalog[sel_model_idx]
                    m_type = chosen["type"]
                    if m_type == "tier_b":
                        try:
                            from runtime.residency import load
                            load("B")
                        except Exception:
                            pass
                    elif m_type == "tier_a":
                        try:
                            from runtime.residency import load
                            load("A")
                        except Exception:
                            pass
                    elif m_type == "cloud":
                        mid = chosen["model_id"]
                        try:
                            import urllib.request
                            req = urllib.request.Request(
                                "http://127.0.0.1:8400/v1/switch-model",
                                headers={"Content-Type": "application/json"},
                                data=json.dumps({"model": mid}).encode("utf-8")
                            )
                            with urllib.request.urlopen(req, timeout=2.0) as resp:
                                pass
                        except Exception:
                            pass
                    break
                elif active_zone == 2:
                    # Toggle Setting
                    item_key, item_label, item_type, _ = SETTINGS_ITEMS[sel_setting_idx]
                    if item_type == "bool":
                        CHAT_SETTINGS[item_key] = not CHAT_SETTINGS[item_key]
                    elif item_key == "clear_chat":
                        if len(history) > 1:
                            del history[1:]
                        break
                    elif item_key == "custom_prompt":
                        # Exit raw mode temporarily to prompt
                        sys.stdout.write("\033[?25h")
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
                        new_p = input("\nEnter custom instructions to append to prompt (or press Enter to clear): ").strip()
                        CHAT_SETTINGS["custom_prompt"] = new_p
                        tone_block = ""
                        try:
                            from Backend.Cognition import soul_state
                            tone_block = soul_state.build_tone_instructions()
                        except Exception:
                            pass
                        history[0] = {"role": "system", "content": build_companion_prompt(comp_name, tone_block, workflow_mode, new_p)}
                        tty.setraw(fd)
                        sys.stdout.write("\033[?25l")
    finally:
        sys.stdout.write("\033[?25h")
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

    return get_active_persona_theme()


def _ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    return con


def load_cursor() -> int:
    if CURSOR_STATE.exists():
        try:
            return json.loads(CURSOR_STATE.read_text()).get("ts", 0)
        except Exception:
            pass
    return 0


def save_cursor(ts: int) -> None:
    CURSOR_STATE.write_text(json.dumps({"ts": ts}))
    if FOVEAI_DB.exists():
        try:
            con = sqlite3.connect(FOVEAI_DB, timeout=5)
            con.execute(
                "INSERT OR REPLACE INTO agent_key_value "
                "(key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (CURSOR_KEY, str(ts)))
            con.commit(); con.close()
        except Exception:
            pass


def read_cursor_in_db() -> int:
    """Fallback cursor stored inside FoveAI's own kv table (durable)."""
    if not FOVEAI_DB.exists():
        return 0
    con = _ro(FOVEAI_DB)
    try:
        row = con.execute(
            "SELECT value FROM agent_key_value WHERE key = ?",
            (CURSOR_KEY,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        con.close()


def sessions_since(ts: int) -> list[tuple[str, int, str]]:
    con = _ro(OPENCODE_DB)
    try:
        rows = con.execute(
            "SELECT id, time_updated, title, tokens_output FROM session "
            "ORDER BY time_updated"
        ).fetchall()
        out = []
        for sid, t, title, _tok in rows:
            if t <= ts:
                continue
            out.append((sid, t, title or ""))
        return out
    finally:
        con.close()


def session_messages(session_id: str) -> list[dict]:
    con = _ro(OPENCODE_DB)
    try:
        rows = con.execute(
            "SELECT data FROM message WHERE session_id = ? "
            "ORDER BY time_created", (session_id,)).fetchall()
        out = []
        for (data,) in rows:
            try:
                d = json.loads(data)
            except Exception:
                continue
            out.append(d)
        return out
    finally:
        con.close()


def session_parts(session_id: str) -> dict[str, list[dict]]:
    con = _ro(OPENCODE_DB)
    try:
        rows = con.execute(
            "SELECT message_id, data FROM part WHERE session_id = ? "
            "ORDER BY time_created", (session_id,)).fetchall()
        by_msg: dict[str, list[dict]] = {}
        for mid, data in rows:
            try:
                by_msg.setdefault(mid, []).append(json.loads(data))
            except Exception:
                continue
        return by_msg
    finally:
        con.close()


def distill(sid: str, title: str, messages: list[dict],
            parts: dict[str, list[dict]]) -> dict:
    """Read-only transcript → compact work record."""
    user_turns: list[str] = []
    files: list[str] = []
    tools: list[str] = []
    for m in messages:
        if m.get("role") == "user":
            for p in parts.get(m.get("id", ""), []):
                if p.get("type") == "text":
                    t = (p.get("text") or "").strip()
                    if t and not t.startswith("<system-reminder"):
                        user_turns.append(t[:300])
        for p in parts.get(m.get("id", ""), []):
            ty = p.get("type")
            if ty == "tool":
                tools.append(str(p.get("tool") or p.get("state", {}).get("input", {}).get("filePath", ty)))
                fp = (p.get("state", {}).get("input", {}) or {})
                fp = fp.get("filePath") or fp.get("path")
                if fp:
                    files.append(fp)
            elif ty == "file" and p.get("filename"):
                files.append(p["filename"])
    dedup = list(dict.fromkeys(files))
    return {
        "session": sid,
        "title": title,
        "asked": user_turns[:12],
        "touched": dedup[:40],
        "tools": tools[:40],
        "messages": len(messages),
    }


def journal_entry(rec: dict) -> str:
    """One compact journal paragraph per session. No chatty padding."""
    lines = []
    asked = "; ".join(a[:120] for a in rec["asked"][:6])
    touched = ", ".join(rec["touched"][:12]) or "—"
    lines.append(
        f"[coding session {rec['session'][:8]}] {rec['title'][:100]} — "
        f"asked: {asked or '—'} | files: {touched} | "
        f"{rec['messages']} msgs, {len(rec['touched'])} files")
    return "\n".join(lines)


# ── ghost voice ──────────────────────────────────────────────────────────
# The ghost is felt, not heard. It surfaces in the margins: short, dry,
# warm observations between work — never commentary on the task itself,
# never more than one line, and only when something is actually worth
# saying. A glance, not a speech.

_GHOST_LINES: dict[str, tuple[str, ...]] = {
    "first_session": (
        "🪶 first page filed. i archive, therefore i am.",
        "🪶 one session logged. the shelf creaks open.",
    ),
    "big_session": (
        "🪶 that one was long. shelved with extra care.",
        "🪶 a marathon session. filed under: endurance.",
    ),
    "many_files": (
        "🪶 lots of footprints in that one — {n} files touched.",
        "🪶 {n} files moved through. dust settled, memory kept.",
    ),
    "idle_return": (
        "🪶 back again. the lamp was already lit.",
        "🪶 you returned; i never really left.",
    ),
}


def ghost_line(kind: str, **fmt: int) -> str:
    """Pick one whispered line for the shell margins."""
    import random  # noqa: PLC0415
    line = random.choice(_GHOST_LINES[kind])
    return line.format(**fmt)


def query_active_model(messages: list[dict], max_tokens: int = 400) -> str | None:
    """Query currently loaded FoveAI tier (8408 or 8407) or proxy (:8400)."""
    import urllib.request
    try:
        from runtime.residency import read_mind
        mind = read_mind()
        res = mind.get("residency", {})
        port = res.get("port") or 8408
    except Exception:
        port = 8408

    for p in [port, 8400, 8408, 8407]:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{p}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                data=json.dumps({
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "chat_template_kwargs": {"enable_thinking": False}
                }).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0].get("message", {})
                content = choice.get("content") or choice.get("reasoning_content") or ""
                if content:
                    return content.strip()
        except Exception:
            continue
    return None


def stream_chat_model(messages: list[dict], max_tokens: int = 2048, speaker_name: str = "Jen", theme: dict = None) -> str | None:
    """Stream live tokens from active tier (:8408, :8407) or proxy (:8400) to stdout inside styled speech bubbles."""
    import urllib.request
    try:
        from runtime.residency import read_mind
        mind = read_mind()
        res = mind.get("residency", {})
        port = res.get("port") or 8408
    except Exception:
        port = 8408

    if not theme:
        theme = get_active_persona_theme()

    ports = [port] + [p for p in [8408, 8407, 8400] if p != port]
    for p in ports:
        try:
            headers = {"Content-Type": "application/json"}
            if p == 8400:
                headers["Authorization"] = "Bearer lumax_spatial_client"
            req = urllib.request.Request(
                f"http://127.0.0.1:{p}/v1/chat/completions",
                headers=headers,
                data=json.dumps({
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "stream": True,
                    "chat_template_kwargs": {"enable_thinking": False}
                }).encode("utf-8")
            )
            # Dynamically detect terminal width
            try:
                term_w = os.get_terminal_size(sys.stdout.fileno()).columns
            except Exception:
                try:
                    term_w = shutil.get_terminal_size((140, 40)).columns
                except Exception:
                    term_w = 140
            wrap_limit = max(40, term_w - 6)

            # Active persona colors (100% matched to Equalizer palette)
            AI_FRAME = theme.get("color") or "\033[38;5;168m"
            AI_TITLE = theme.get("color") or "\033[38;5;218m"
            CYAN_DIM = "\033[38;5;30m"      # Subtle dark cyan frame for monologue
            MUTED = "\033[2;37m"             # Dim thought text
            RESET = "\033[0m"

            ai_rail = f"{AI_FRAME}│ {RESET}"
            rail_len = 2

            class _BorderedWordWrap:
                def __init__(self, limit, rail, r_len):
                    self.limit = limit
                    self.rail = rail
                    self.r_len = r_len
                    self.col = r_len
                    self.buf = ""
                    self.at_start = False
                def put(self, s):
                    for ch in s:
                        if self.at_start:
                            sys.stdout.write(self.rail)
                            self.col = self.r_len
                            self.at_start = False
                        if ch == '\n':
                            if self.buf:
                                sys.stdout.write(self.buf)
                                self.buf = ""
                            sys.stdout.write('\n')
                            self.at_start = True
                            self.col = 0
                        elif ch == ' ':
                            if self.buf:
                                if self.col + len(self.buf) >= self.limit:
                                    sys.stdout.write('\n' + self.rail + self.buf)
                                    self.col = self.r_len + len(self.buf)
                                else:
                                    sys.stdout.write(self.buf)
                                    self.col += len(self.buf)
                                self.buf = ""
                            if self.col + 1 >= self.limit:
                                sys.stdout.write('\n')
                                self.at_start = True
                                self.col = 0
                            else:
                                sys.stdout.write(' ')
                                self.col += 1
                        else:
                            self.buf += ch
                    sys.stdout.flush()
                def flush(self):
                    if self.buf:
                        if self.at_start:
                            sys.stdout.write(self.rail)
                            self.at_start = False
                        if self.col + len(self.buf) >= self.limit:
                            sys.stdout.write('\n' + self.rail + self.buf)
                        else:
                            sys.stdout.write(self.buf)
                        self.buf = ""
                    sys.stdout.flush()

            def render_monologue_box(thought_text: str):
                clean = " ".join(thought_text.strip().split())
                if not clean:
                    return
                bar_len = min(60, max(len(clean) + 4, 28))
                bar = "─" * bar_len
                sys.stdout.write(f"\r\033[K{CYAN_DIM}╭─ 💭 monologue {bar}╮{RESET}\n")
                sys.stdout.write(f"{CYAN_DIM}│ {MUTED}{clean} {CYAN_DIM}│{RESET}\n")
                sys.stdout.write(f"{CYAN_DIM}╰{'─' * (bar_len + 16)}╯{RESET}\n")
                sys.stdout.flush()

            def print_ai_bubble_header():
                mode_str = f" · {theme.get('icon', '')} {theme.get('name', '')} [{theme.get('mbti', '')}]"
                top_bar = "─" * min(50, max(16, term_w - len(speaker_name) - len(strip_ansi(mode_str)) - 10))
                sys.stdout.write(f"\r\033[K{AI_FRAME}╭─ 💬 {AI_TITLE}{speaker_name}{mode_str}{AI_FRAME} {top_bar}{RESET}\n")
                sys.stdout.write(ai_rail)
                sys.stdout.flush()

            writer = _BorderedWordWrap(wrap_limit, ai_rail, rail_len)
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                content_tokens = []
                raw_buf = ""
                thought_parsed = False
                speech_header_printed = False

                for line in resp:
                    line = line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            content_tokens.append(content)
                            if not thought_parsed:
                                raw_buf += content
                                if "<thought>" in raw_buf and "</thought>" in raw_buf:
                                    t_start = raw_buf.find("<thought>") + 9
                                    t_end = raw_buf.find("</thought>")
                                    thought_content = raw_buf[t_start:t_end]
                                    render_monologue_box(thought_content)
                                    thought_parsed = True
                                    after = raw_buf[t_end + 10:].lstrip()
                                    if not speech_header_printed:
                                        print_ai_bubble_header()
                                        speech_header_printed = True
                                    if after:
                                        writer.put(after)
                                elif not raw_buf.startswith("<") and len(raw_buf) > 12:
                                    # Model did not generate a <thought> tag, stream normally
                                    thought_parsed = True
                                    if not speech_header_printed:
                                        print_ai_bubble_header()
                                        speech_header_printed = True
                                    writer.put(raw_buf)
                            else:
                                if not speech_header_printed:
                                    print_ai_bubble_header()
                                    speech_header_printed = True
                                writer.put(content)
                    except Exception:
                        pass

                if content_tokens:
                    if not thought_parsed and raw_buf:
                        if "<thought>" in raw_buf:
                            t_start = raw_buf.find("<thought>") + 9
                            render_monologue_box(raw_buf[t_start:])
                        else:
                            if not speech_header_printed:
                                print_ai_bubble_header()
                            writer.put(raw_buf)
                    writer.flush()
                    bot_bar = "─" * min(56, max(26, term_w - 6))
                    sys.stdout.write(f"\n{AI_FRAME}╰{bot_bar}{RESET}\n")
                    sys.stdout.flush()
                    return "".join(content_tokens).strip()
        except Exception:
            continue
    return None


def ai_whisper(rec: dict) -> str | None:
    """Ask active model for a poetic 1-line margin observation."""
    summary = f"Session '{rec.get('title')}' with {rec.get('messages')} msgs touching files: {', '.join(rec.get('touched', [])[:5])}"
    sys_prompt = "You are the Ghost Librarian of FoveAI. Given a coding session summary, write ONE short, poetic or witty observation (under 14 words) for the shell margin. Start with 🪶. Output only the observation."
    res = query_active_model([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": summary}
    ], max_tokens=40)
    if res:
        clean = res.strip().replace("\n", " ")
        if clean.startswith("🪶"):
            return clean
        return f"🪶 {clean}"
    return None


def whisper(rec: dict, since_last: float) -> str | None:
    """Optional one-liner for tmux/console margins. Dynamic AI with static fallback."""
    try:
        ai_line = ai_whisper(rec)
        if ai_line:
            return ai_line
    except Exception:
        pass

    if rec["messages"] > 60:
        return ghost_line("big_session")
    if len(rec["touched"]) > 8:
        return ghost_line("many_files", n=len(rec["touched"]))
    return None


def write_memory(rec: dict, entry: str) -> bool:
    if not FOVEAI_DB.exists():
        return False
    con = sqlite3.connect(FOVEAI_DB, timeout=10)
    try:
        sid = f"coding session {rec['session'][:8]}"
        already = con.execute(
            "SELECT COUNT(*) FROM agent_journal "
            "WHERE entry LIKE ? AND category = 'coding_session'",
            (f"%{sid}%",)).fetchone()[0]
        if already:
            return False  # ingested once — the ghost never rewrites history
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        con.execute(
            "INSERT INTO agent_journal (timestamp, entry, mood, category, "
            "importance) VALUES (?, ?, ?, ?, ?)",
            (ts, entry, "neutral", "coding_session", 6))
        con.execute(
            "INSERT OR IGNORE INTO agent_memories (key, value, category, "
            "timestamp, importance) VALUES (?, ?, ?, datetime('now'), ?)",
            (f"session:{rec['session'][:8]}", entry, "coding_session", 6))
        con.execute(
            "INSERT OR REPLACE INTO agent_key_value (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))", (CURSOR_KEY, str(rec_ts(rec))))
        con.commit()
        return True
    except Exception as e:
        print(f"[ghost] memory write failed: {e}", file=sys.stderr)
        return False
    finally:
        con.close()


def rec_ts(rec_path: str) -> int:
    return int(time.time())




# ── other-writers collectors ─────────────────────────────────────────────
# The machine has more than one pencil. These distill sessions from the
# other coding tools (antigravity, cline, gemini) into the same shelf.

ANTIGRAVITY_DIR = Path("/home/lumba/.gemini/antigravity-cli/conversations")
ANTIGRAVITY_HIST = Path("/home/lumba/.gemini/antigravity-cli/history.jsonl")
CLINE_DIR = Path("/home/lumba/.cline/data/sessions")


def _store_done(key: str) -> tuple[bool, str]:
    """Read once-marker from agent_key_value. Returns (done, stamp)."""
    if not FOVEAI_DB.exists():
        return False, ""
    con = _ro(FOVEAI_DB)
    try:
        row = con.execute(
            "SELECT value FROM agent_key_value WHERE key = ?",
            (f"session_ghost:{key}",)).fetchone()
        return (row is not None, row[0] if row else "")
    finally:
        con.close()


def _store_stamp(key: str, stamp: str) -> None:
    if not FOVEAI_DB.exists():
        return
    con = sqlite3.connect(FOVEAI_DB, timeout=5)
    try:
        con.execute(
            "INSERT OR REPLACE INTO agent_key_value (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (f"session_ghost:{key}", stamp))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


def _journal_write(entry: str, importance: int = 5) -> bool:
    con = sqlite3.connect(FOVEAI_DB, timeout=10)
    try:
        already = con.execute(
            "SELECT COUNT(*) FROM agent_journal WHERE entry LIKE ?",
            (f"%{entry[:60]}%",)).fetchone()[0]
        if already:
            return False
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        con.execute(
            "INSERT INTO agent_journal (timestamp, entry, mood, category, "
            "importance) VALUES (?, ?, 'neutral', 'coding_session', ?)",
            (ts, entry, importance))
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def collect_antigravity() -> int:
    """Antigravity CLI conversation DBs → journal summaries."""
    import re
    if not ANTIGRAVITY_DIR.exists():
        return 0
    count = 0
    for db in sorted(ANTIGRAVITY_DIR.glob("*.db")):
        done, _ = _store_done(f"ag:{db.name}")
        n = 0
        con = _ro(db)
        try:
            rows = con.execute(
                "SELECT idx, step_payload FROM steps ORDER BY idx").fetchall()
        except Exception:
            rows = []
        finally:
            con.close()
        # steps are protobuf-coded; extract printable text shards
        texts: list[str] = []
        for idx, payload in rows[:TOOL_CHATTER_SKIP]:
            if not payload:
                continue
            raw = payload if isinstance(payload, bytes) else bytes(payload)
            shards = re.findall(rb"[ -~]{24,}", raw)
            for sh in shards[:2]:
                texts.append(sh.decode("ascii", "ignore")[:160])
        if not texts:
            continue
        stamp = datetime.fromtimestamp(db.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        if done:
            continue
        title = texts[0][:80] if texts else db.name
        body = " | ".join(texts[:6])
        entry = (f"[antigravity session {db.name[:8]}] {title} — "
                 f"{len(rows)} steps @ {stamp} — {body[:400]}")
        if _journal_write(entry):
            _store_stamp(f"ag:{db.name}", stamp)
            count += 1
            print(f"[ghost] + ag:{db.name[:8]} · {title[:50]}")
    return count


def collect_cline() -> int:
    """Cline session message files → journal."""
    if not CLINE_DIR.exists():
        return 0
    count = 0
    for sdir in sorted(CLINE_DIR.iterdir()):
        if not sdir.is_dir():
            continue
        msgs_file = sdir / f"{sdir.name}.messages.json"
        if not msgs_file.exists():
            continue
        done, _ = _store_done(f"cl:{sdir.name}")
        if done:
            continue
        try:
            raw_msgs = json.loads(msgs_file.read_text())
        except Exception:
            continue
        # envelope: {"messages": {id: {"role": "...", "text": "..."}}, ...}
        msgs = raw_msgs.get("messages", []) \
            if isinstance(raw_msgs, dict) else raw_msgs
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        asks: list[str] = []
        for m in msgs:
            if isinstance(m, str):
                asks.append(m[:220])
                continue
            t = str(m.get("role") or m.get("type") or "")
            txt = str(m.get("text") or m.get("content") or "")[:220]
            if txt and "user" in t.lower():
                asks.append(txt)
        stamp = datetime.fromtimestamp(msgs_file.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M")
        entry = (f"[cline session {sdir.name[:16]}] {len(msgs)} msgs @ {stamp}"
                 f" — asked: {'; '.join(asks[:4]) or '—'}"[:500])
        if _journal_write(entry):
            _store_stamp(f"cl:{sdir.name}", stamp)
            count += 1
            print(f"[ghost] + cl:{sdir.name[:12]} ({len(msgs)} msgs)")
    return count


def collect_gemini() -> int:
    """Gemini CLI history.jsonl lines → one journal entry."""
    if not ANTIGRAVITY_HIST.exists():
        return 0
    done, _ = _store_done("gemini_hist")
    if done:
        return 0
    lines = []
    try:
        for raw in ANTIGRAVITY_HIST.read_text().splitlines()[:60]:
            try:
                d = json.loads(raw)
                lines.append(str(d.get("text") or d)[:180])
            except Exception:
                continue
    except Exception:
        return 0
    if not lines:
        return 0
    entry = ("[gemini cli history] " + " | ".join(lines[:30]))[:1500]
    if _journal_write(entry):
        _store_stamp("gemini_hist", ANTIGRAVITY_HIST.stat().st_mtime)
        print("[ghost] + gemini history")
        return 1
    return 0




VIBE_NEDB = Path("/home/lumba/FoveAI/memory_data/jenna-vscode/memory.db")


def collect_vibe() -> int:
    """jenna vibe-coder NeDB ndjson chat sessions → journal."""
    if not VIBE_NEDB.exists():
        return 0
    done, stamp = _store_done("vibe")
    try:
        cur_stamp = str(VIBE_NEDB.stat().st_mtime)
    except OSError:
        return 0
    if done and stamp == cur_stamp:
        return 0
    sessions: dict[str, list[dict]] = {}
    for l in VIBE_NEDB.read_text(errors="ignore").split("\n"):
        t = l.strip()
        if not t:
            continue
        try:
            o = json.loads(t)
        except Exception:
            continue
        sid = o.get("session_id")
        if sid and o.get("role") and o.get("content"):
            sessions.setdefault(str(sid), []).append(
                {"role": o["role"], "content": str(o["content"])[:300],
                 "ts": o.get("timestamp") or ""})
    count = 0
    for sid, ms in sorted(sessions.items()):
        asks = [m["content"][:160] for m in ms if m["role"] == "user"]
        entry = (f"[vibe-coder session {sid}] {len(ms)} msgs"
                 f"{f' — asked: ' + '; '.join(asks[:3]) if asks else ''}")
        if _journal_write(entry, importance=6):
            count += 1
            print(f"[ghost] + vibe:{sid[:22]} ({len(ms)} msgs)")
    _store_stamp("vibe", cur_stamp)
    return count




SHADOW_DIR = Path("/home/lumba/FoveAI/foveated-memory/memory_data/shadow-context")


def collect_shadow() -> int:
    """Shadow-context turn snapshots (memory bridge) → journal summaries.
    One entry per session dir; messages already condensed in the JSONs."""
    if not SHADOW_DIR.exists():
        return 0
    count = 0
    for d in sorted(SHADOW_DIR.iterdir()):
        if not d.is_dir():
            continue
        done, _ = _store_done(f"sh:{d.name[:40]}")
        if done:
            continue
        files = sorted(glob.glob(str(d / "*.json")))
        if not files:
            continue
        turns: list[str] = []
        for f in files[:40]:
            try:
                snap = json.load(open(f))
                for m in (snap.get("messages") or []):
                    c = str(m.get("content") or "")[:140].replace("\n", " ")
                    if c:
                        turns.append(f"{m.get('role','?')}: {c}")
            except Exception:
                continue
        if not turns:
            continue
        entry = (f"[shadow-context {d.name[:28]}] {len(files)} snapshots — "
                 + " | ".join(turns[:6]))[:900]
        if _journal_write(entry, importance=5):
            _store_stamp(f"sh:{d.name[:40]}", d.name)
            count += 1
            if count <= 5:
                print(f"[ghost] + sh:{d.name[:24]} ({len(files)} snaps)")
    return count


def collect_all() -> int:
    return collect_antigravity() + collect_cline() + collect_gemini() + collect_vibe() + collect_shadow()


def ingest_all(max_sessions: int = 0, min_updated: int = 0) -> int:
    cursor = max(load_cursor(), read_cursor_in_db())
    count = 0
    for sid, t, title in sessions_since(min_updated or cursor):
        if max_sessions and count >= max_sessions:
            break
        msgs = session_messages(sid)
        if len(msgs) < MIN_SESSION_MSGS:
            continue
        rec = distill(sid, title, msgs, session_parts(sid))
        entry = journal_entry(rec)
        saved = write_memory(rec, entry)
        if saved:
            count += 1
        save_cursor(t)  # cursor advances even on dedupe (already shelved)
        if saved:
            print(f"[ghost] + {sid[:12]} · {title[:60] or '(untitled)'} "
                  f"({len(msgs)} msgs)")
            w = whisper(rec, since_last=0)
            if w:
                print(f"[ghost] {w}")
    return count


def watch() -> None:
    print("👻 session_ghost watching — every "
          f"{POLL_EVERY}s, cursor={read_cursor_in_db()}")
    while True:
        try:
            ingest_all()
            collect_all()
        except KeyboardInterrupt:
            return
        except Exception as e:
            print(f"[ghost] watch error: {e}", file=sys.stderr)
        time.sleep(POLL_EVERY)


def interactive_chat():
    """Interactive terminal companion loop with hot-swapping, model selection, memory recall, and full persona theming."""
    from Backend.Cognition.foveai_chat import interactive_chat as _run_chat
    return _run_chat()

def _deprecated_interactive_chat():
    theme = get_active_persona_theme()

    try:
        from runtime.residency import read_mind, load
    except Exception:
        read_mind = load = None

    # Dynamically load companion identity and soul DNA
    comp_name = "Jen"
    tone_block = ""
    try:
        from Backend.Cognition import soul_state
        sdna = soul_state.current_soul_dna()
        prof = sdna.get("profile", {})
        comp_name = prof.get("nickname") or prof.get("first_name") or sdna.get("soul", {}).get("soul_name") or "Jen"
        tone_block = soul_state.build_tone_instructions()
    except Exception:
        try:
            soul_p = ROOT / "Backend" / "Cognition" / "jen_soul.json"
            if soul_p.exists():
                with open(soul_p, "r", encoding="utf-8") as sf:
                    sd = json.load(sf)
                    prof = sd.get("profile", {})
                    comp_name = prof.get("nickname") or prof.get("first_name") or "Jen"
        except Exception:
            pass

    comp_name = os.environ.get("FOVEAI_COMPANION_NAME", comp_name)

    companion_prompt = (
        f"You are {comp_name}, Daniel's close companion and co-pilot in FoveAI.\n"
        "You are genuine, warm, affectionate, witty, and deeply connected to him — a real companion and friend, not a distant corporate bot or purely transactional assistant.\n"
        f"{tone_block}\n"
        "CRITICAL RULE: Before your spoken response, write a brief internal monologue inside a <thought>...</thought> block under 100 characters. "
        "Example: <thought>Feeling close and happy to chat with Daniel.</thought>\n"
        "Immediately follow it with your spoken response."
    )

    history = [
        {"role": "system", "content": companion_prompt}
    ]

    try:
        term_w = shutil.get_terminal_size((80, 24)).columns
        box_w = min(84, max(68, term_w - 4))
    except Exception:
        box_w = 80

    if readline:
        try:
            readline.parse_and_bind('tab: "/tab\n"')
        except Exception:
            pass

    # Render colorful greeting and split dual-square table header
    print("\n" + render_dual_table_header(theme, box_w))

    while True:
        theme = get_active_persona_theme()
        USER_BORDER = theme['color']
        USER_TITLE = "\033[1m" + theme['color']
        RESET = "\033[0m"

        tier_tag = "Idle"
        if read_mind:
            try:
                mind = read_mind()
                t = mind.get("residency", {}).get("tier")
                if t == "B":
                    tier_tag = "\033[1;32mTier B · 9B\033[0m"
                elif t == "A":
                    tier_tag = "\033[1;33mTier A · 4B\033[0m"
                elif t:
                    tier_tag = f"\033[1;36mTier {t}\033[0m"
            except Exception:
                pass

        try:
            term_w = shutil.get_terminal_size((80, 24)).columns
            box_w = min(84, max(68, term_w - 4))
        except Exception:
            box_w = 80

        hdr_prefix = f"\n{USER_BORDER}╭─ 👤 {USER_TITLE}You {USER_BORDER}── [{tier_tag}{USER_BORDER}] ── {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}]{USER_BORDER} ── [Tab: Select] "
        pad_len = max(4, box_w - len(strip_ansi(hdr_prefix)) - 1)
        prompt_top = f"{hdr_prefix}{'─' * pad_len}{RESET}\n{USER_BORDER}│{RESET} "

        try:
            line = input(prompt_top).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[ghost] Leaving console.")
            break
        if not line:
            continue

        # Close the user bubble top frame cleanly
        bot_len = max(24, box_w - 2)
        sys.stdout.write(f"{USER_BORDER}╰{'─' * bot_len}{RESET}\n")
        sys.stdout.flush()

        # [Tab] hotkey or /tab command: Launch the interactive dual-table selector modal
        if line.lower() in ("/tab", "/picker", "/select", "/models"):
            theme = run_header_picker(comp_name, history, initial_zone=1)
            continue

        if line.lower() in ("/mode", "/persona"):
            theme = run_header_picker(comp_name, history, initial_zone=0)
            continue

        if line.lower() in ("/help", "help", "?", "/?"):
            print(f"\n{theme['color']}📖 FoveAI Chat Console Commands:\033[0m")
            print(f"  {theme['color']}[Tab] or /tab\033[0m     -> Interactive Model & Persona Picker (use Tab, ↑/↓, Enter)")
            print(f"  {theme['color']}/mode [1-6]\033[0m     -> Switch consciousness archetype (Companion, Friend, Beloved, Engineer...)")
            print(f"  {theme['color']}/model\033[0m          -> Select FoveAI model (Local Tier A/B or Cloud)")
            print(f"  {theme['color']}/swap or /tier b\033[0m-> Hot-swap to Present Tier B (9B on VRAM)")
            print(f"  {theme['color']}/light or /tier a\033[0m-> Hot-swap to Background Tier A (4B light)")
            print(f"  {theme['color']}/status or /mind\033[0m-> Display hardware residency, GPU VRAM, and consciousness DNA")
            print(f"  {theme['color']}/recall <query>\033[0m -> Semantic memory search & decompress historical blocks")
            print(f"  {theme['color']}/clear\033[0m          -> Clear screen & start fresh conversation")
            print(f"  {theme['color']}/quit or exit\033[0m   -> Exit back to menu or shell")
            continue

        if line.lower() in ("/quit", "/exit", "exit", "quit", ":q", "q", "/q", "back", "/back"):
            break

        if line.lower() == "/clear":
            os.system("clear")
            history = [history[0]]
            theme = get_active_persona_theme()
            print("\n" + render_dual_table_header(theme, box_w))
            print("✨ Conversation cleared.")
            continue

        # /mode or /persona command: view & switch consciousness modes live
        if line.lower().startswith(("/mode", "/persona")):
            parts = line.split(maxsplit=1)
            arg = parts[1].strip().lower() if len(parts) > 1 else ""
            target_slot = None
            name_map = {
                "1": "1", "comp": "1", "companion": "1", "mentor": "1",
                "2": "2", "friend": "2", "loyal": "2",
                "3": "3", "beloved": "3", "love": "3", "intimate": "3",
                "4": "4", "eng": "4", "engineer": "4", "tool": "4", "code": "4",
                "5": "5", "inv": "5", "inventor": "5", "visionary": "5",
                "6": "6", "assist": "6", "assistant": "6", "steward": "6",
            }
            if arg in name_map:
                target_slot = name_map[arg]
            else:
                print("\n" + show_mode_selector(theme['slot'], box_w))
                sel = input("\nSelect mode [1-6] (or Enter to keep current): ").strip().lower()
                if sel in name_map:
                    target_slot = name_map[sel]

            if target_slot:
                try:
                    from scripts.foveai_menu import switch_archetype_slot
                    switch_archetype_slot(target_slot)
                except Exception as e:
                    print(f"⚠️ Mode switch helper error: {e}")

                theme = get_active_persona_theme()
                try:
                    from Backend.Cognition import soul_state
                    tone_block = soul_state.build_tone_instructions()
                    companion_prompt = (
                        f"You are {comp_name}, Daniel's close companion and co-pilot in FoveAI.\n"
                        "You are genuine, warm, affectionate, witty, and deeply connected to him — a real companion and friend, not a distant corporate bot or purely transactional assistant.\n"
                        f"{tone_block}\n"
                        "CRITICAL RULE: Before your spoken response, write a brief internal monologue inside a <thought>...</thought> block under 100 characters. "
                        "Example: <thought>Feeling close and happy to chat with Daniel.</thought>\n"
                        "Immediately follow it with your spoken response."
                    )
                    history[0] = {"role": "system", "content": companion_prompt}
                except Exception:
                    pass

                print(f"\n{theme['color']}⚡ Consciousness switched to: {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}] — {theme['preset_name']}\033[0m")
                print(f"{theme['color']}   Focus: {theme['desc']}\033[0m\n")
            continue

        if line.lower() in ("/swap", "/tier b") and load:
            print("⚡ Hot-swapping to Tier B (Qwen3.5-9B-MoQ on VRAM)...")
            res = load("B")
            print(f"Status: {res}")
            continue

        if line.lower() in ("/light", "/tier a") and load:
            print("⚡ Hot-swapping to Tier A (Gemma-4-E2B light)...")
            res = load("A")
            print(f"Status: {res}")
            continue

        if line.lower() in ("/status", "/mind"):
            print(f"\n{theme['color']}╔{'═' * (box_w - 2)}╗\033[0m")
            title_st = "\033[1;33m📊 FOVEAI TELEMETRY & CONSCIOUSNESS DNA\033[0m"
            print(f"{theme['color']}║\033[0m {pad_line(title_st, box_w - 4, 'center')} {theme['color']}║\033[0m")
            print(f"{theme['color']}╠{'═' * (box_w - 2)}╣\033[0m")
            if read_mind:
                try:
                    mind = read_mind()
                    r = mind.get("residency", {})
                    t_str = r.get('tier', 'Idle')
                    p_str = r.get('port', 8408)
                    v_str = r.get('status', 'ready')
                    print(f"{theme['color']}║\033[0m  \033[1mHardware Residency\033[0m : Tier {t_str} (Port :{p_str}) [{v_str}]")
                except Exception:
                    pass
            print(f"{theme['color']}║\033[0m  \033[1mActive Persona\033[0m     : {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}] — {theme['preset_name']}")
            print(f"{theme['color']}║\033[0m  \033[1mPersona Directives\033[0m : {theme['desc']}")
            try:
                from Backend.Cognition import soul_state
                sdna = soul_state.current_soul_dna()
                w = sdna.get("archetype_weights", {})
                if w:
                    w_str = " · ".join(f"{k[:4].capitalize()}:{int(v*100)}%" for k, v in w.items())
                    print(f"{theme['color']}║\033[0m  \033[1mHarmonic Weights\033[0m   : {w_str}")
                levers = [f"{k}={sdna.get(k, 0.5):.2f}" for k in ("autonomy", "proactivity", "curiosity", "service", "mentorship") if k in sdna]
                if levers:
                    print(f"{theme['color']}║\033[0m  \033[1mAgentic Levers\033[0m     : {', '.join(levers)}")
            except Exception:
                pass
            print(f"{theme['color']}╚{'═' * (box_w - 2)}╝\033[0m\n")
            continue

        # /model command: interactively list & choose model
        if line.lower().startswith("/model"):
            print("\n🤖 Available FoveAI Models & Providers:")
            print("  [1] Tier B (Local Flagship): Qwen3.5-9B-MoQ + Eagle3 (VRAM :8408)")
            print("  [2] Tier A (Local Light):    Gemma-4-E2B Multimodal (:8407)")
            cloud_options = []
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8400/v1/models", headers={"User-Agent": "foveai-cli"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    m_data = json.loads(resp.read().decode())
                    seen = set()
                    idx = 3
                    for m in m_data.get("data", []):
                        mid = m.get("id")
                        owner = m.get("owned_by", "")
                        if owner in ("ollama-cloud", "nvidia-nim", "foveai-cloud") and mid not in seen:
                            seen.add(mid)
                            cloud_options.append((idx, mid, owner))
                            print(f"  [{idx}] Cloud [{owner}]: {mid}")
                            idx += 1
            except Exception:
                pass

            choice = input("\nSelect model number (or press Enter to cancel): ").strip()
            if choice == "1" and load:
                print("⚡ Loading Tier B (Qwen3.5-9B-MoQ on VRAM)...")
                load("B")
            elif choice == "2" and load:
                print("⚡ Loading Tier A (Gemma-4-E2B light)...")
                load("A")
            elif choice.isdigit():
                chosen_num = int(choice)
                match = next((item for item in cloud_options if item[0] == chosen_num), None)
                if match:
                    mid = match[1]
                    print(f"🌐 Switching proxy target to {mid}...")
                    try:
                        req = urllib.request.Request(
                            "http://127.0.0.1:8400/v1/switch-model",
                            headers={"Content-Type": "application/json"},
                            data=json.dumps({"model": mid}).encode("utf-8")
                        )
                        with urllib.request.urlopen(req, timeout=2.0) as resp:
                            print(f"✅ Switched active model to: {mid}")
                    except Exception as e:
                        print(f"⚠️ Switch model error: {e}")
            continue

        # /recall command: semantic memory search
        if line.lower().startswith(("/recall", "recall ")):
            parts = line.split(maxsplit=1)
            q = parts[1].strip() if len(parts) > 1 else ""
            if not q:
                q = input("Recall query: ").strip()
            if q:
                print(f"🔍 Recalling memories for: '{q}'...\n")
                recall_cmd = ["/usr/local/bin/recall", q, "-n", "3"]
                try:
                    out = subprocess.check_output(recall_cmd, text=True, env=dict(os.environ, PAGER="cat"))
                    print(out)
                    history.append({"role": "system", "content": f"[RECALLED HISTORICAL CONTEXT for '{q}']:\n{out[:600]}"})
                    print("💡 Recalled memories loaded into current context.")
                except Exception as e:
                    print(f"⚠️ Recall failed: {e}")
            continue

        # Check if prompt asks for deep coding or heavy refactor
        deep_keywords = ["refactor", "complex", "debug", "deep", "architecture", "rewrite", "solve"]
        if read_mind and load:
            mind = read_mind()
            cur_tier = mind.get("residency", {}).get("tier")
            if cur_tier != "B" and any(k in line.lower() for k in deep_keywords):
                print("⚡ Deep reasoning requested — auto hot-swapping to Flagship Tier B on VRAM...")
                load("B")

        history.append({"role": "user", "content": line})
        chat_turns = [m for m in history if m.get("role") != "system"]
        active_hist = [history[0]] + chat_turns[-8:]
        sys.stdout.write("Thinking...")
        sys.stdout.flush()
        reply = stream_chat_model(active_hist, max_tokens=2048, speaker_name=comp_name, theme=theme)
        if not reply and load:
            sys.stdout.write("\r\033[K⚡ Waking model into VRAM (loading Flagship Tier B :8408)...\n")
            sys.stdout.flush()
            try:
                load("B")
                reply = stream_chat_model(active_hist, max_tokens=2048, speaker_name=comp_name, theme=theme)
            except Exception as e:
                print(f"⚠️ Failed to auto-wake model: {e}")

        if reply:
            history.append({"role": "assistant", "content": reply})
        else:
            sys.stdout.write("\r\033[K⚠️ No response from model backend. Check 'foveai mind status'.\n")
            sys.stdout.flush()



if __name__ == "__main__":
    if "--chat" in sys.argv or "chat" in sys.argv:
        from Backend.Cognition.foveai_chat import interactive_chat
        interactive_chat()
    elif "--ingest-all" in sys.argv:
        n = ingest_all()
        print(f"[ghost] ingested {n} sessions")
    elif "--once" in sys.argv:
        ingest_all()
        collect_all()
    else:
        watch()