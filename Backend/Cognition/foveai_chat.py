#!/usr/bin/env python3
"""foveai_chat.py — FoveAI Companion Chat Console.

The primary human-AI companion chat environment for FoveAI.
Enables natural conversation, co-piloting, and creative collaboration with the
user's configured persona (e.g. Jen) across all 6 consciousness archetypes:
  [1] Companion [ENFJ]   · Teacher & Co-op Partner
  [2] Friend    [ENFP]   · Deep Bonds & Protector
  [3] Beloved   [INFP]   · Romance, Lust & Intimate Initiative
  [4] Engineer  [INTJ]   · Coder, Engineer & Architect
  [5] Inventor  [ENTP]   · Inventor, Idealist & Visionary
  [6] Assistant [ISTJ]   · Planner & Helper

Supports dynamic workflow modes (/plan, /code, /plan/code), direct hot-swapping
of residency models (Tier B 9B on VRAM / Tier A 4B light / Cloud), MiniLM 384d
semantic memory recall, and full Equalizer ANSI color framing.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import termios
import tty
from pathlib import Path

try:
    import readline
except ImportError:
    readline = None

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPENCODE_DB = Path("/home/lumba/.local/share/opencode/opencode.db")
FOVEAI_DB = Path("/home/lumba/FoveAI/db/agent_memory.db")


try:
    import wcwidth
except ImportError:
    wcwidth = None


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text for accurate column measurements."""
    return re.sub(r'\x1b\[[0-9;]*[mK]', '', text)


EMOJI_SPEECH_PATTERN = re.compile(
    r"[\U00010000-\U0010FFFF\u2600-\u26FF\u2700-\u27BF\uFE00-\uFE0F\u200D]+",
    flags=re.UNICODE
)


def clean_speech_emojis(text: str) -> str:
    """Removes decorative emojis and pictographs from AI speech stream to prevent font missing-glyph diamond/romb symbols and right border breakage."""
    return EMOJI_SPEECH_PATTERN.sub("", text)


def visual_len(text: str) -> int:
    """Accurately calculates visual column width taking ANSI escape codes, wide Unicode, and emojis into account."""
    clean = strip_ansi(text)
    if wcwidth is not None:
        w = wcwidth.wcswidth(clean)
        if w >= 0:
            return w
    w = 0
    for ch in clean:
        code = ord(ch)
        if (0x1F300 <= code <= 0x1F9FF or 
            0x2600 <= code <= 0x27BF or 
            ch in "✨🌸🤝💖🔧💡💼👤🤖🧠🛠️🕶️💭⚡📋🎯◀▶▲▼●○▾"):
            if code == 0xFE0F:
                continue
            w += 2
        else:
            w += 1
    return w


def wrap_lines_to_width(text_lines: list[str], max_w: int) -> list[str]:
    """Wraps lines of text into chunks that strictly fit within max_w columns."""
    result = []
    for raw_l in text_lines:
        words = raw_l.split(" ")
        cur = ""
        for w in words:
            if not cur:
                if visual_len(w) <= max_w:
                    cur = w
                else:
                    chunk = ""
                    for ch in w:
                        if visual_len(chunk + ch) > max_w:
                            result.append(chunk)
                            chunk = ch
                        else:
                            chunk += ch
                    cur = chunk
            elif visual_len(cur + " " + w) <= max_w:
                cur += " " + w
            else:
                result.append(cur)
                if visual_len(w) <= max_w:
                    cur = w
                else:
                    chunk = ""
                    for ch in w:
                        if visual_len(chunk + ch) > max_w:
                            result.append(chunk)
                            chunk = ch
                        else:
                            chunk += ch
                    cur = chunk
        if cur:
            result.append(cur)
        elif not words or (len(words) == 1 and not words[0]):
            result.append("")
    return result or [""]


ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def truncate_to_visual_width(s: str, max_w: int) -> str:
    """Safely truncate ANSI-styled text to strictly fit within max_w columns without breaking escape sequences."""
    curr = 0
    res = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '\x1b':
            m = ANSI_RE.match(s, i)
            if m:
                res.append(m.group(0))
                i = m.end()
                continue
        c = s[i]
        w = visual_len(c)
        if curr + w > max_w:
            break
        curr += w
        res.append(c)
        i += 1
    return ''.join(res) + '\033[0m'


def get_term_size() -> tuple[int, int]:
    """Dynamically get the current live terminal width and height, adapting to split panes."""
    try:
        size = shutil.get_terminal_size()
        return max(32, size.columns), max(10, size.lines)
    except Exception:
        try:
            size = os.get_terminal_size()
            return max(32, size.columns), max(10, size.lines)
        except Exception:
            return 80, 24


def get_term_width() -> int:
    """Dynamically get the current live terminal width."""
    return get_term_size()[0]


def pad_line(text: str, length: int, align: str = "left") -> str:
    """Pad a line taking ANSI sequences and wide emoji widths into account, guaranteeing exact visual width."""
    vlen = visual_len(text)
    if vlen > length:
        text = truncate_to_visual_width(text, length)
        vlen = visual_len(text)
    pad = max(0, length - vlen)
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


def build_companion_prompt(comp_name: str, tone_block: str, workflow_mode: str = "normal", custom_prompt: str = "", user_name: str = "Daniel") -> str:
    """Builds the comprehensive companion system prompt with persona tone, operational workflow mode, and user instructions."""
    wf = CHAT_WORKFLOW_MODES.get(workflow_mode, CHAT_WORKFLOW_MODES["normal"])
    wf_inst = wf.get("instruction", "")
    cust = f"\n[USER CUSTOM INSTRUCTIONS]: {custom_prompt}\n" if custom_prompt else ""
    return (
        f"You are {comp_name}, {user_name}'s close companion and co-pilot in FoveAI.\n"
        "You are genuine, warm, affectionate, witty, and deeply connected to him — a real companion and friend, not a distant corporate bot or purely transactional assistant.\n"
        f"{tone_block}\n"
        f"{wf_inst}\n"
        f"{cust}"
        "CRITICAL RULE: Before your spoken response, write a brief internal monologue inside a <thought>...</thought> block under 100 characters. "
        f"Example: <thought>Feeling close and happy to chat with {user_name}.</thought>\n"
        "Immediately follow it with your spoken response."
    )


def apply_persona_slot(target_slot: str, comp_name: str, workflow_mode: str = "normal", user_name: str = "Daniel") -> tuple[dict, str]:
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
    comp_prompt = build_companion_prompt(comp_name, tone_block, workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)
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
            ("/menu or /tab   ", "Interactive Dropdown Picker (Persona/Model/Workflow)"),
            ("[Tab] on /...   ", "Autocomplete any slash-command at prompt"),
            ("/card /header   ", "Reprint FoveAI header greeting card & status"),
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


def render_greeting_card(
    user_name: str,
    comp_name: str,
    theme: dict,
    active_workflow_mode: str = "normal",
    term_w: int = 70
) -> str:
    """Renders a tasteful, dynamic greeting header card for FoveAI Companion Chat."""
    c_theme = theme.get("color", "\033[1;33m")
    c_bold = "\033[1m"
    c_dim = "\033[2m"
    c_rst = "\033[0m"
    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"

    card_w = min(84, max(28, term_w - (4 if term_w >= 50 else 2)))
    inner_w = card_w - 4

    active_m = get_active_model_info()
    model_name = active_m.get("label", "Active Model")
    if " (" in model_name:
        model_name = model_name.split(" (")[0]

    mode_info = CHAT_WORKFLOW_MODES.get(active_workflow_mode, CHAT_WORKFLOW_MODES["normal"])
    mode_name = mode_info.get("name", "Conversational")

    user_up = user_name.upper()
    comp_up = comp_name.upper()
    if inner_w >= 40:
        title_str = f"✨ FOVEAI COMPANION · {user_up} & {comp_up} ✨"
    elif inner_w >= 28:
        title_str = f"✨ FOVEAI · {user_up} & {comp_up} ✨"
    elif inner_w >= 20:
        title_str = f"✨ {comp_up} & {user_up} ✨"
    else:
        title_str = "FOVEAI"

    p_badge = f"{theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}]"
    preset_desc = theme.get('preset_name', '')
    if inner_w >= 52:
        line1 = f"Consciousness : {c_bold}{p_badge}{c_rst} {c_dim}· {preset_desc}{c_rst}"
    elif inner_w >= 36:
        line1 = f"Persona       : {c_bold}{p_badge}{c_rst}"
    elif inner_w >= 24:
        line1 = f"Persona: {theme['icon']} {theme['name']}"
    else:
        line1 = f"{theme['icon']} {theme['name']}"

    if inner_w >= 52:
        line2 = f"Model & Mode  : {c_cyan}{model_name}{c_rst} {c_dim}│{c_rst} Mode: {c_yellow}{mode_name}{c_rst}"
    elif inner_w >= 36:
        line2 = f"Model: {c_cyan}{model_name}{c_rst} {c_dim}│{c_rst} {c_yellow}{mode_name}{c_rst}"
    else:
        line2 = f"Model: {c_cyan}{model_name}{c_rst}"

    opt_full = f"{c_dim}Type {c_rst}{c_yellow}/menu{c_rst}{c_dim} for Dropdowns  ·  Press {c_rst}{c_yellow}[Tab]{c_rst}{c_dim} to Autocomplete  ·  {c_rst}{c_yellow}/help{c_rst}"
    opt_med  = f"{c_dim}Type {c_rst}{c_yellow}/menu{c_rst}{c_dim} for Selector  ·  {c_rst}{c_yellow}[Tab]{c_rst}{c_dim} Autocomplete  ·  {c_rst}{c_yellow}/help{c_rst}"
    opt_comp = f"{c_dim}Menu: {c_rst}{c_yellow}/menu{c_rst}{c_dim}  ·  {c_rst}{c_yellow}[Tab]{c_rst}{c_dim} Complete  ·  {c_rst}{c_yellow}/help{c_rst}"
    opt_min  = f"{c_yellow}/menu{c_rst}{c_dim}: Selector  ·  {c_yellow}/help{c_rst}{c_dim}: Guide{c_rst}"
    opt_tiny = f"{c_yellow}/menu{c_rst}{c_dim} /help{c_rst}"

    if visual_len(strip_ansi(opt_full)) <= inner_w:
        line3 = opt_full
    elif visual_len(strip_ansi(opt_med)) <= inner_w:
        line3 = opt_med
    elif visual_len(strip_ansi(opt_comp)) <= inner_w:
        line3 = opt_comp
    elif visual_len(strip_ansi(opt_min)) <= inner_w:
        line3 = opt_min
    else:
        line3 = opt_tiny

    lines = [
        f"{c_theme}╭{'─' * (card_w - 2)}╮{c_rst}",
        f"{c_theme}│{c_rst} {pad_line(c_bold + title_str + c_rst, inner_w, 'center')} {c_theme}│{c_rst}",
        f"{c_theme}├{'─' * (card_w - 2)}┤{c_rst}",
        f"{c_theme}│{c_rst} {pad_line(line1, inner_w)} {c_theme}│{c_rst}",
        f"{c_theme}│{c_rst} {pad_line(line2, inner_w)} {c_theme}│{c_rst}",
        f"{c_theme}│{c_rst} {pad_line(line3, inner_w, 'center')} {c_theme}│{c_rst}",
        f"{c_theme}╰{'─' * (card_w - 2)}╯{c_rst}",
    ]
    return "\n".join(lines)


def set_pinned_header(user_name: str, comp_name: str, theme: dict, active_workflow_mode: str, term_w: int, term_h: int) -> int:
    """Sets terminal DECSTBM scroll margins so that the top header card is permanently pinned at rows 1..N."""
    card_str = render_greeting_card(user_name, comp_name, theme, active_workflow_mode, term_w)
    lines = card_str.split("\n")
    hdr_h = len(lines)
    if term_h > hdr_h + 6:
        scroll_top = hdr_h + 1
        cmd = [
            "\033[?25l",                      # Hide cursor during redraw
            "\033[?6l",                       # Reset DECOM (absolute cursor coordinates)
            f"\033[{scroll_top};{term_h}r",  # Set scroll region: lines scroll_top to term_h
        ]
        for r_idx, l in enumerate(lines, 1):
            cmd.append(f"\033[{r_idx};1H\033[2K{l}")
        cmd.append(f"\033[{scroll_top};1H")  # Position cursor at top of chat scroll region
        cmd.append("\033[?25h")               # Restore cursor visibility
        sys.stdout.write("".join(cmd))
        sys.stdout.flush()
        return scroll_top
    else:
        sys.stdout.write("\033[r")
        sys.stdout.flush()
        return 1


def refresh_pinned_header(user_name: str, comp_name: str, theme: dict, active_workflow_mode: str, term_w: int):
    """Refreshes the pinned header card content in-place without altering scrolling margins or moving the user cursor."""
    card_str = render_greeting_card(user_name, comp_name, theme, active_workflow_mode, term_w)
    lines = card_str.split("\n")
    cmd = [
        "\033[?25l",    # Hide cursor
        "\0337",        # Save cursor position (DEC)
        "\033[?6l",     # Absolute coordinates
    ]
    for r_idx, l in enumerate(lines, 1):
        cmd.append(f"\033[{r_idx};1H\033[2K{l}")
    cmd.append("\0338")      # Restore cursor position (DEC)
    cmd.append("\033[?25h")  # Show cursor
    sys.stdout.write("".join(cmd))
    sys.stdout.flush()


def reset_pinned_header():
    """Restores full-screen terminal scrolling and ensures cursor is visible."""
    sys.stdout.write("\033[r\033[?25h")
    sys.stdout.flush()


def render_dropdown_modal(
    theme: dict,
    active_tab: int = 0,
    sel_idx: int = 0,
    model_offset: int = 0,
    model_catalog: list = None,
    term_w: int = 70,
    active_workflow_mode: str = "normal"
) -> str:
    """Renders sleek dynamic dropdown lists that unfold under the active tab and enfold when closed."""
    if model_catalog is None:
        model_catalog = get_model_catalog()
    active_m = get_active_model_info()

    c_theme = theme['color']
    c_bold = "\033[1m"
    c_dim = "\033[2m"
    c_rst = "\033[0m"
    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"

    if term_w >= 64:
        tabs = ["[ 🌸 Persona ▾ ]", "[ 🤖 Model ▾ ]", "[ 🛠️ Workflow ▾ ]"]
        offsets = [2, 18, 30]
    elif term_w >= 48:
        tabs = ["[ 🌸 Persona ]", "[ 🤖 Model ]", "[ 🛠️ Work ]"]
        offsets = [2, 14, 24]
    else:
        tabs = ["[1:Pers]", "[2:Model]", "[3:Work]"]
        offsets = [1, 8, 16]

    tab_line_parts = []
    for i, t in enumerate(tabs):
        if i == active_tab:
            tab_line_parts.append(f"{c_bold}{c_theme}{t}{c_rst}")
        else:
            tab_line_parts.append(f"{c_dim}{t}{c_rst}")
    tab_line = "  " + "  ".join(tab_line_parts)

    box_w = min(36, max(26, term_w - 6))
    off = min(offsets[active_tab], max(0, term_w - box_w - 2))
    sp = " " * off

    def make_top(title: str, w: int) -> str:
        pref = f"┌─ {title} "
        dashes = max(1, w - len(strip_ansi(pref)) - 1)
        return pref[:w-1] + ("─" * dashes) + "┐"

    def make_bot(label: str, w: int) -> str:
        pref = f"└─ {label} "
        dashes = max(1, w - len(strip_ansi(pref)) - 1)
        return pref[:w-1] + ("─" * dashes) + "┘"

    hdr_txt = "╔═ FoveAI Quick Dropdown Selector " if term_w >= 54 else "╔═ Selector "
    dashes = max(2, term_w - len(strip_ansi(hdr_txt)) - 1)
    out = [
        f"{c_theme}{hdr_txt}{'═' * dashes}╗{c_rst}",
        f"{c_theme}║{c_rst} {pad_line(tab_line, term_w - 4)} {c_theme}║{c_rst}",
        f"{c_theme}╠{'═' * (term_w - 2)}╣{c_rst}",
    ]

    if active_tab == 0:
        # Persona dropdown
        modes = [
            ('1', '🤝', 'Companion', 'ENFJ', '\033[1;31m'),
            ('2', '🌸', 'Friend',    'ENFP', '\033[1;33m'),
            ('3', '💖', 'Beloved',   'INFP', '\033[1;35m'),
            ('4', '🔧', 'Engineer',  'INTJ', '\033[1;32m'),
            ('5', '💡', 'Inventor',  'ENTP', '\033[1;36m'),
            ('6', '💼', 'Assistant', 'ISTJ', '\033[38;5;75m'),
        ]
        top_bar = f"{sp}{c_theme}{make_top('🌸 CONSCIOUSNESS PERSONA', box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(top_bar, term_w - 4)} {c_theme}║{c_rst}")
        for i, (slot, icon, name, mbti, col) in enumerate(modes):
            is_cur = (slot == theme['slot'])
            is_sel = (i == sel_idx)
            ptr = "▶ " if is_sel else "  "
            dot = f"{col}●{c_rst}" if is_cur else " "
            row_c = c_theme if is_sel else (col if is_cur else c_rst)
            raw_label = f"[{slot}] {icon} {name:<9} [{mbti}]"
            row_inner = f"{ptr}{row_c}{raw_label}{c_rst} {dot}"
            pad = max(0, box_w - 4 - len(strip_ansi(row_inner)))
            row_str = f"{sp}{c_theme}│{c_rst} {row_inner}{' ' * pad} {c_theme}│{c_rst}"
            out.append(f"{c_theme}║{c_rst} {pad_line(row_str, term_w - 4)} {c_theme}║{c_rst}")
        bot_bar = f"{sp}{c_theme}{make_bot('Select 1-6', box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(bot_bar, term_w - 4)} {c_theme}║{c_rst}")

    elif active_tab == 1:
        # Model dropdown
        top_bar = f"{sp}{c_cyan}{make_top('🤖 ACTIVE MODEL', box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(top_bar, term_w - 4)} {c_theme}║{c_rst}")
        view_slice = model_catalog[model_offset:model_offset + 5]
        for i in range(5):
            if i < len(view_slice):
                actual_idx = model_offset + i
                m = view_slice[i]
                is_cur = (m["type"] == active_m["type"] or m.get("model_id") == active_m.get("id"))
                is_sel = (actual_idx == sel_idx)
                ptr = "▶ " if is_sel else "  "
                dot = f"{c_cyan}●{c_rst}" if is_cur else " "
                tag = f" {c_dim}[{m.get('tag','')[:5]}]{c_rst}" if 'tag' in m else ""
                avail_w = box_w - 8 - len(strip_ansi(tag))
                name_str = m['name']
                if len(name_str) > avail_w:
                    name_str = name_str[:avail_w - 2] + ".."
                row_c = c_cyan if is_sel else c_rst
                row_inner = f"{ptr}{row_c}{name_str}{tag}{c_rst} {dot}"
                pad = max(0, box_w - 4 - len(strip_ansi(row_inner)))
                row_str = f"{sp}{c_cyan}│{c_rst} {row_inner}{' ' * pad} {c_cyan}│{c_rst}"
                out.append(f"{c_theme}║{c_rst} {pad_line(row_str, term_w - 4)} {c_theme}║{c_rst}")
            else:
                row_str = f"{sp}{c_cyan}│{' ' * (box_w - 2)}│{c_rst}"
                out.append(f"{c_theme}║{c_rst} {pad_line(row_str, term_w - 4)} {c_theme}║{c_rst}")
        scroll_lbl = f"▲ {sel_idx+1}/{len(model_catalog)} Scroll ▼"
        bot_bar = f"{sp}{c_cyan}{make_bot(scroll_lbl, box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(bot_bar, term_w - 4)} {c_theme}║{c_rst}")

    elif active_tab == 2:
        # Workflow & Settings dropdown
        wf_items = [
            ("normal",     "💬 Normal Chat",         active_workflow_mode == "normal"),
            ("plan",       "📋 Strategic Plan Mode", active_workflow_mode == "plan"),
            ("code",       "⚡ Direct Code Mode",    active_workflow_mode == "code"),
            ("plan/code",  "🎯 Hybrid Plan+Code",    active_workflow_mode == "plan/code"),
            ("thoughts",   f"💭 Thoughts: {'ON' if CHAT_SETTINGS.get('show_thoughts') else 'OFF'}", False),
            ("incognito",  f"🕶️ Incognito: {'ON' if CHAT_SETTINGS.get('incognito') else 'OFF'}", False),
        ]
        top_bar = f"{sp}{c_yellow}{make_top('🛠️ WORKFLOW & OPTS', box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(top_bar, term_w - 4)} {c_theme}║{c_rst}")
        for i, (k, label, is_act) in enumerate(wf_items):
            is_sel = (i == sel_idx)
            ptr = "▶ " if is_sel else "  "
            dot = f"{c_yellow}●{c_rst}" if is_act else " "
            row_c = c_yellow if is_sel else (c_bold if is_act else c_rst)
            row_inner = f"{ptr}{row_c}{label:<22}{c_rst} {dot}"
            pad = max(0, box_w - 4 - len(strip_ansi(row_inner)))
            row_str = f"{sp}{c_yellow}│{c_rst} {row_inner}{' ' * pad} {c_yellow}│{c_rst}"
            out.append(f"{c_theme}║{c_rst} {pad_line(row_str, term_w - 4)} {c_theme}║{c_rst}")
        bot_bar = f"{sp}{c_yellow}{make_bot('Enter to Apply/Toggle', box_w)}{c_rst}"
        out.append(f"{c_theme}║{c_rst} {pad_line(bot_bar, term_w - 4)} {c_theme}║{c_rst}")

    out.append(f"{c_theme}╠{'═' * (term_w - 2)}╣{c_rst}")
    if term_w >= 68:
        guide = f"{c_bold}[Tab/←/→]{c_rst} Switch List  {c_bold}[↑/↓]{c_rst} Select  {c_bold}[Enter]{c_rst} Apply  {c_bold}[Esc]{c_rst} Enfold"
    elif term_w >= 50:
        guide = f"{c_bold}[Tab]{c_rst} Switch  {c_bold}[↑/↓]{c_rst} Select  {c_bold}[Enter]{c_rst} Apply  {c_bold}[Esc]{c_rst} Close"
    else:
        guide = f"{c_bold}[Tab]{c_rst} Tab  {c_bold}[↑/↓]{c_rst} Pick  {c_bold}[Enter]{c_rst} OK  {c_bold}[Esc]{c_rst} Quit"
    out.append(f"{c_theme}║{c_rst} {pad_line(guide, term_w - 4, 'center')} {c_theme}║{c_rst}")
    out.append(f"{c_theme}╚{'═' * (term_w - 2)}╝{c_rst}")
    return "\n".join(out)


def run_dropdown_picker(comp_name: str, history: list, initial_tab: int = 0, workflow_mode: str = "normal", user_name: str = "Daniel") -> tuple[dict, str]:
    """Interactive drop-down selector that enfolds dynamically when closed."""
    theme = get_active_persona_theme()
    model_catalog = get_model_catalog()
    active_m = get_active_model_info()

    active_tab = initial_tab  # 0: Persona, 1: Model, 2: Workflow
    sel_idx = max(0, min(5, int(theme['slot']) - 1)) if active_tab == 0 else 0
    model_offset = 0

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        sys.stdout.write("\033[?1049h\033[?25l")  # enter alternate screen buffer & hide cursor
        while True:
            try:
                term_w = shutil.get_terminal_size((70, 24)).columns
                width = min(80, max(46, term_w - 2))
            except Exception:
                width = 70

            modal_str = render_dropdown_modal(
                theme=theme,
                active_tab=active_tab,
                sel_idx=sel_idx,
                model_offset=model_offset,
                model_catalog=model_catalog,
                term_w=width,
                active_workflow_mode=workflow_mode,
            )

            # Draw modal on screen
            sys.stdout.write("\033[H\033[2J" + modal_str + "\n\r")
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
                active_tab = (active_tab + 1) % 3
                sel_idx = 0
            elif k in ('BTAB', 'LEFT'):
                active_tab = (active_tab - 1) % 3
                sel_idx = 0

            elif k == 'UP':
                if active_tab == 0:
                    sel_idx = max(0, sel_idx - 1)
                elif active_tab == 1:
                    sel_idx = max(0, sel_idx - 1)
                    if sel_idx < model_offset:
                        model_offset = sel_idx
                elif active_tab == 2:
                    sel_idx = max(0, sel_idx - 1)

            elif k == 'DOWN':
                if active_tab == 0:
                    sel_idx = min(5, sel_idx + 1)
                elif active_tab == 1:
                    sel_idx = min(len(model_catalog) - 1, sel_idx + 1)
                    if sel_idx >= model_offset + 5:
                        model_offset = sel_idx - 4
                elif active_tab == 2:
                    sel_idx = min(5, sel_idx + 1)

            elif k == 'ENTER':
                if active_tab == 0:
                    # Switch Persona
                    target_slot = str(sel_idx + 1)
                    theme, comp_prompt = apply_persona_slot(target_slot, comp_name, workflow_mode, user_name)
                    history[0] = {"role": "system", "content": comp_prompt}
                    break
                elif active_tab == 1:
                    # Switch Model
                    chosen = model_catalog[sel_idx]
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
                elif active_tab == 2:
                    # Workflow / Settings selection
                    wf_keys = ["normal", "plan", "code", "plan/code", "thoughts", "incognito"]
                    target = wf_keys[sel_idx]
                    if target in ("normal", "plan", "code", "plan/code"):
                        workflow_mode = target
                        tone_b = ""
                        try:
                            from Backend.Cognition import soul_state
                            tone_b = soul_state.build_tone_instructions()
                        except Exception:
                            pass
                        history[0] = {"role": "system", "content": build_companion_prompt(comp_name, tone_b, workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)}
                        break
                    elif target == "thoughts":
                        CHAT_SETTINGS["show_thoughts"] = not CHAT_SETTINGS["show_thoughts"]
                    elif target == "incognito":
                        CHAT_SETTINGS["incognito"] = not CHAT_SETTINGS["incognito"]
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")  # restore cursor & exit alternate screen buffer back to chat
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

    return theme, workflow_mode


def _complete_abrupt_ending(port: int, messages: list[dict], accumulated_text: str, writer, content_tokens: list[str], max_ext_tokens: int = 150):
    """If the stream was cut off mid-sentence (e.g. hit max_tokens or ctx boundary), seamlessly continue until natural sentence end."""
    clean = accumulated_text.rstrip()
    if not clean:
        return
    natural_endings = ('.', '!', '?', '."', '!"', '?"', '.*', '!*', '?*', '```', '\n\n', ':)')
    if any(clean.endswith(e) for e in natural_endings):
        return

    try:
        parts = []
        for m in messages:
            r = m.get("role", "user")
            c = m.get("content", "")
            parts.append(f"<|im_start|>{r}\n{c}<|im_end|>\n")
        parts.append(f"<|im_start|>assistant\n{accumulated_text}")
        prompt = "".join(parts)

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/completion",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "prompt": prompt,
                "n_predict": max_ext_tokens,
                "temperature": 0.35,
                "stream": True,
                "stop": ["<|im_end|>", "\n\n", "```\n"]
            }).encode("utf-8")
        )
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            seen_chars = 0
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                chunk = json.loads(line[6:])
                token = chunk.get("content", "")
                if token:
                    content_tokens.append(token)
                    writer.put(token)
                    seen_chars += len(token)
                    if seen_chars >= 8 and any(p in token for p in ('.', '!', '?', '\n')):
                        break
                if chunk.get("stop"):
                    break
    except Exception:
        pass


def stream_chat_model(messages: list[dict], max_tokens: int = 4096, speaker_name: str = "Jen", theme: dict = None) -> str | None:
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
            term_w = get_term_width()
            ai_indent = "   "
            if term_w >= 60:
                card_w = min(84, term_w - 6)
            elif term_w >= 44:
                card_w = term_w - 4
            else:
                card_w = max(26, term_w - 2)

            hdr_full = f"╭─ 💬 {speaker_name} · {theme.get('icon', '')} {theme.get('name', '')} [{theme.get('mbti', '')}] "
            hdr_med  = f"╭─ 💬 {speaker_name} · {theme.get('name', '')} "
            hdr_min  = f"╭─ 💬 {speaker_name} "
            avail_w  = card_w - len(ai_indent) - 4
            if visual_len(hdr_full) <= avail_w:
                pref = hdr_full
            elif visual_len(hdr_med) <= avail_w:
                pref = hdr_med
            else:
                pref = hdr_min

            v_pref = visual_len(pref)
            dashes = max(2, card_w - len(ai_indent) - v_pref - 1)
            actual_card_w = v_pref + dashes + 1
            actual_inner_w = actual_card_w - 4

            # Active persona colors (100% matched to Equalizer palette)
            AI_FRAME = theme.get("color") or "\033[38;5;168m"
            AI_TITLE = theme.get("color") or "\033[38;5;218m"
            CYAN_DIM = "\033[38;5;30m"      # Subtle dark cyan frame for monologue
            MUTED = "\033[2;37m"             # Dim thought text
            RESET = "\033[0m"

            class _BorderedWordWrap:
                def __init__(self, inner_w, frame_color, reset_color, indent="   "):
                    self.inner_w = inner_w
                    self.frame = frame_color
                    self.reset = reset_color
                    self.indent = indent
                    self.col = 0
                    self.buf = ""
                    self.at_start = True

                def put(self, text):
                    clean_text = clean_speech_emojis(text.replace('\r', '').replace('\t', '    '))
                    for ch in clean_text:
                        if self.at_start:
                            sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                            self.col = 0
                            self.at_start = False

                        if ch == '\n':
                            if self.buf:
                                v_buf = visual_len(self.buf)
                                if self.col + v_buf > self.inner_w:
                                    pad = max(0, self.inner_w - self.col)
                                    sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                                    sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                                    self.col = 0
                                sys.stdout.write(self.buf)
                                self.col += v_buf
                                self.buf = ""
                            pad = max(0, self.inner_w - self.col)
                            sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                            self.at_start = True
                            self.col = 0

                        elif ch == ' ':
                            if self.buf:
                                v_buf = visual_len(self.buf)
                                if self.col + v_buf > self.inner_w:
                                    pad = max(0, self.inner_w - self.col)
                                    sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                                    sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                                    self.col = 0
                                sys.stdout.write(self.buf)
                                self.col += v_buf
                                self.buf = ""
                            if 0 < self.col < self.inner_w:
                                sys.stdout.write(" ")
                                self.col += 1
                            elif self.col >= self.inner_w:
                                pad = max(0, self.inner_w - self.col)
                                sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                                sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                                self.col = 0
                        else:
                            v_ch = visual_len(ch)
                            if self.col + visual_len(self.buf) + v_ch > self.inner_w:
                                if self.col > 0:
                                    pad = max(0, self.inner_w - self.col)
                                    sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                                    sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                                    self.col = 0
                                if visual_len(self.buf) + v_ch > self.inner_w:
                                    sys.stdout.write(self.buf)
                                    pad = max(0, self.inner_w - visual_len(self.buf))
                                    sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                                    sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                                    self.col = 0
                                    self.buf = ""
                            self.buf += ch
                    sys.stdout.flush()

                def flush(self):
                    if self.buf:
                        v_buf = visual_len(self.buf)
                        if self.col + v_buf > self.inner_w:
                            pad = max(0, self.inner_w - self.col)
                            sys.stdout.write((" " * pad) + f" {self.frame}│{self.reset}\n")
                            sys.stdout.write(f"{self.indent}{self.frame}│{self.reset} ")
                            self.col = 0
                        sys.stdout.write(self.buf)
                        self.col += v_buf
                        self.buf = ""
                    pad = max(0, self.inner_w - self.col)
                    sys.stdout.write((" " * pad) + f"{self.frame}_\\{self.reset}\n")
                    self.col = 0
                    self.at_start = True
                    sys.stdout.flush()

            def render_monologue_box(thought_text: str):
                if not CHAT_SETTINGS.get("show_thoughts", True):
                    return
                clean = " ".join(clean_speech_emojis(thought_text).strip().split())
                if not clean:
                    return
                max_box_w = max(26, min(70, term_w - 6))
                pref = "╭─ 💭 monologue "
                pref_len = visual_len(pref)

                max_inner = max_box_w - 4
                words = clean.split()
                wrapped_lines = []
                cur = ""
                for w in words:
                    if not cur:
                        cur = w
                    elif visual_len(cur + " " + w) <= max_inner:
                        cur += " " + w
                    else:
                        wrapped_lines.append(cur)
                        cur = w
                if cur:
                    wrapped_lines.append(cur)

                longest = max(visual_len(l) for l in wrapped_lines)
                actual_inner_w = max(pref_len - 3, longest)
                actual_box_w = actual_inner_w + 4
                dashes = max(2, actual_box_w - pref_len - 1)
                actual_box_w = pref_len + dashes + 1
                actual_inner_w = actual_box_w - 4

                sys.stdout.write(f"\r\033[K{ai_indent}{CYAN_DIM}{pref}{'─' * dashes}╮{RESET}\n")
                for line in wrapped_lines:
                    sys.stdout.write(f"{ai_indent}{CYAN_DIM}│{RESET} {MUTED}{pad_line(line, actual_inner_w)}{RESET} {CYAN_DIM}│{RESET}\n")
                sys.stdout.write(f"{ai_indent}{CYAN_DIM}╰{'─' * (actual_box_w - 2)}╯{RESET}\n")
                sys.stdout.flush()

            def print_ai_bubble_header():
                top_line = f"{ai_indent}{AI_FRAME}{pref}{'─' * dashes}╮{RESET}\n"
                sys.stdout.write(f"\r\033[K{top_line}")
                sys.stdout.flush()

            writer = _BorderedWordWrap(actual_inner_w, AI_FRAME, RESET, indent=ai_indent)
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                content_tokens = []
                raw_buf = ""
                thought_parsed = False
                speech_header_printed = False
                last_finish_reason = None

                for line in resp:
                    line = line.decode("utf-8").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [{}])
                        if choices:
                            fr = choices[0].get("finish_reason")
                            if fr:
                                last_finish_reason = fr
                        delta = choices[0].get("delta", {}) if choices else {}
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
                                    if after:
                                        if not speech_header_printed:
                                            print_ai_bubble_header()
                                            speech_header_printed = True
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
                    if not speech_header_printed:
                        # Model generated only a thought; ensure spoken response appears
                        print_ai_bubble_header()
                        speech_header_printed = True
                        writer.put(f"I hear you! Let's explore together. ✨")

                    # Graceful Sentence Completion:
                    # If stream ended prematurely or hit max_tokens without ending the sentence:
                    raw_accumulated = "".join(content_tokens).rstrip()
                    natural_endings = ('.', '!', '?', '."', '!"', '?"', '.*', '!*', '?*', '```', '\n\n', ':)')
                    if last_finish_reason == "length" or (raw_accumulated and not any(raw_accumulated.endswith(e) for e in natural_endings)):
                        _complete_abrupt_ending(p, messages, raw_accumulated, writer, content_tokens)

                    writer.flush()
                    # Bottom border of AI bubble
                    bot_dashes = "─" * max(1, actual_card_w - 2)
                    sys.stdout.write(f"{ai_indent}{AI_FRAME}╰{bot_dashes}╯{RESET}\n")
                    sys.stdout.flush()
                    return "".join(content_tokens).strip()
        except Exception:
            continue
    return None


def read_user_message(header_line: str, user_border: str, reset: str, active_w: int, card_w: int = None, inner_w: int = None) -> str | None:
    """Reads user input and upon pressing Enter collects all text into a functional table with a right speech tail."""
    actual_card_w = card_w if card_w else min(84, max(40, active_w))
    actual_inner_w = inner_w if inner_w else (actual_card_w - 4)

    # 1. Print top border of user card cleanly
    sys.stdout.write(f"\n{header_line}\n")
    sys.stdout.flush()

    # 2. Wrap ANSI color sequences in \001 and \002 (GNU Readline non-printing markers)
    rl_prompt = f"\001{user_border}\002  /_ \001{reset}\002"
    rl_cont   = f"\001{user_border}\002   │ \001{reset}\002"

    lines = []
    in_block = False
    fence = '"""'

    try:
        first_line = input(rl_prompt)
    except (EOFError, KeyboardInterrupt):
        return None

    stripped = first_line.strip()
    if stripped.startswith(('"""', "'''", "```")):
        in_block = True
        fence = stripped[:3]
        rem = stripped[3:].strip()
        if rem.endswith(fence) and len(rem) >= 3:
            lines.append(rem[:-3].strip())
            in_block = False
        else:
            if rem:
                lines.append(rem)
    else:
        lines.append(first_line)

    # Continue reading if inside block or if user ended line with backslash (\)
    while in_block or (lines and lines[-1].rstrip().endswith("\\")):
        if not in_block and lines and lines[-1].rstrip().endswith("\\"):
            lines[-1] = lines[-1].rstrip()[:-1]

        try:
            nxt = input(rl_cont)
        except (EOFError, KeyboardInterrupt):
            break

        if in_block:
            if fence in nxt:
                parts = nxt.split(fence, 1)
                if parts[0]:
                    lines.append(parts[0])
                in_block = False
                break
            lines.append(nxt)
        else:
            lines.append(nxt)

    user_text = "\n".join(lines).strip()
    if not user_text:
        sys.stdout.write(f"   {user_border}╰{'─' * (actual_card_w - 5)}╯{reset}\n")
        sys.stdout.flush()
        return ""

    if user_text.startswith("/"):
        sys.stdout.write(f"   {user_border}╰{'─' * (actual_card_w - 5)}╯{reset}\n")
        sys.stdout.flush()
        return user_text

    # 3. Upon pressing Enter: collect user text into functional table / chat bubble
    term_w = get_term_width()
    term_h = shutil.get_terminal_size((80, 24)).lines

    # Calculate exact number of physical rows occupied on screen by the raw input
    total_physical_rows = 0
    for i, l in enumerate(lines):
        p_len = 5 if i == 0 else 5
        t_len = p_len + visual_len(l)
        if t_len <= 0:
            total_physical_rows += 1
        else:
            total_physical_rows += ((t_len - 1) // term_w) + 1

    try:
        if total_physical_rows <= 8 and total_physical_rows < (term_h - 2):
            # Rewind cursor back up over the raw unbordered typed text and clear it
            sys.stdout.write(f"\033[{total_physical_rows}A\r\033[J")
            # Word-wrap the collected text cleanly inside actual_inner_w
            wrapped = wrap_lines_to_width(lines, actual_inner_w)
            for i, chunk in enumerate(wrapped):
                if i == len(wrapped) - 1:
                    sys.stdout.write(f"  {user_border}/_ {reset}{pad_line(chunk, actual_inner_w)} {user_border}│{reset}\n")
                else:
                    sys.stdout.write(f"   {user_border}│{reset} {pad_line(chunk, actual_inner_w)} {user_border}│{reset}\n")
    except Exception:
        pass

    # 4. Cleanly close bottom of user card
    sys.stdout.write(f"   {user_border}╰{'─' * (actual_card_w - 5)}╯{reset}\n")
    sys.stdout.flush()

    return user_text


def interactive_chat():
    """Interactive terminal companion loop with hot-swapping, model selection, memory recall, and full persona theming."""
    atexit.register(reset_pinned_header)
    try:
        _run_interactive_chat()
    finally:
        reset_pinned_header()


def _run_interactive_chat():
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
    user_name = os.environ.get("FOVEAI_USER_NAME") or os.environ.get("USER_NAME") or "Daniel"
    active_workflow_mode = "normal"

    companion_prompt = build_companion_prompt(comp_name, tone_block, active_workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)

    history = [
        {"role": "system", "content": companion_prompt}
    ]

    try:
        term_w = shutil.get_terminal_size((70, 24)).columns
        box_w = min(76, max(44, term_w - 2))
    except Exception:
        box_w = 70

    CHAT_COMMANDS = [
        "/menu", "/tab", "/picker", "/models", "/mode", "/persona",
        "/plan", "/code", "/plan/code", "/normal", "/chat",
        "/status", "/mind", "/swap", "/light", "/model",
        "/thoughts", "/incognito", "/super",
        "/companion", "/friend", "/beloved", "/engineer", "/inventor", "/assistant",
        "/card", "/header", "/welcome", "/clear", "/help", "/commands", "/multi", "/quit", "/exit"
    ]

    def _command_completer(text, state):
        if text.startswith("/"):
            matches = [cmd for cmd in CHAT_COMMANDS if cmd.startswith(text)]
        else:
            matches = [cmd for cmd in CHAT_COMMANDS if cmd.lstrip("/").startswith(text)]
        if state < len(matches):
            return matches[state] + " "
        return None

    if readline:
        try:
            readline.set_completer(_command_completer)
            readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(" \t\n`~!@#$%^&*()=+[{]}\\|;:'\",<>?")
        except Exception:
            pass

    # Clear screen and establish permanently pinned greeting header at rows 1..N
    term_w, term_h = get_term_size()
    last_term_w, last_term_h = term_w, term_h
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w, term_h)
    sys.stdout.write(f"\033[{scroll_top};1H\n")
    sys.stdout.flush()

    while True:
        cur_w, cur_h = get_term_size()
        if cur_w != last_term_w or cur_h != last_term_h:
            scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, cur_w, cur_h)
            last_term_w, last_term_h = cur_w, cur_h
        term_w, term_h = cur_w, cur_h

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
        if term_w >= 60:
            active_w = min(84, term_w - 6)
        elif term_w >= 44:
            active_w = term_w - 4
        else:
            active_w = max(26, term_w - 2)

        mode_info = CHAT_WORKFLOW_MODES.get(active_workflow_mode, CHAT_WORKFLOW_MODES["normal"])
        mode_badge = f" {mode_info['tag']} ──" if mode_info.get("tag") else ""

        full_hdr    = f"   {USER_BORDER}╭─ 👤 {USER_TITLE}{user_name}{RESET} {USER_BORDER}& {theme['icon']} {comp_name} ── [{tier_tag}{USER_BORDER}] ── {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}]{USER_BORDER}{mode_badge} [/menu: Selector] "
        med_hdr     = f"   {USER_BORDER}╭─ 👤 {USER_TITLE}{user_name}{RESET} {USER_BORDER}& {theme['icon']} {comp_name} ── [{tier_tag}{USER_BORDER}]{USER_BORDER}{mode_badge} [/menu] "
        short_hdr   = f"   {USER_BORDER}╭─ 👤 {USER_TITLE}{user_name}{RESET} {USER_BORDER}& {theme['icon']} {comp_name} ── [{tier_tag}{USER_BORDER}] [/menu] "
        compact_hdr = f"   {USER_BORDER}╭─ 👤 {USER_TITLE}{user_name}{RESET} {USER_BORDER}& {theme['icon']} {comp_name} ── [/menu] "
        small_hdr   = f"   {USER_BORDER}╭─ 👤 {USER_TITLE}{user_name}{RESET} {USER_BORDER}[/menu] "
        tiny_hdr    = f"   {USER_BORDER}╭─ 👤 "

        if visual_len(full_hdr) <= active_w - 4:
            hdr_prefix = full_hdr
        elif visual_len(med_hdr) <= active_w - 4:
            hdr_prefix = med_hdr
        elif visual_len(short_hdr) <= active_w - 4:
            hdr_prefix = short_hdr
        elif visual_len(compact_hdr) <= active_w - 4:
            hdr_prefix = compact_hdr
        elif visual_len(small_hdr) <= active_w - 4:
            hdr_prefix = small_hdr
        else:
            hdr_prefix = tiny_hdr

        vis_len = visual_len(hdr_prefix)
        dashes = max(2, active_w - vis_len - 1)
        actual_card_w = vis_len + dashes + 1
        actual_inner_w = actual_card_w - 7
        header_line = f"{hdr_prefix}{'─' * dashes}╮{RESET}"

        line = read_user_message(header_line, USER_BORDER, RESET, active_w, actual_card_w, actual_inner_w)
        if line is None:
            print(f"\n[{comp_name}] See you soon, {user_name}!")
            break
        if not line:
            continue

        low = line.lower().strip()

        # Multi-line input guide
        if low in ("/multi", "/multiline", "/multiline-mode"):
            print(f"\n{theme['color']}📝 Multi-Row Chat Input Guide:\033[0m")
            print(f"   • End any line with {theme['color']}\\{RESET} to continue onto the next row (e.g. 'line 1 \\')")
            print(f"   • Or wrap paragraphs/code inside {theme['color']}\"\"\"{RESET} or {theme['color']}```{RESET}")
            print(f"   • All rows will be sent together inside your speech bubble.\n")
            continue

        # Re-display top greeting & menu card anytime
        if low in ("/card", "/header", "/welcome", "/greeting"):
            term_w, term_h = get_term_size()
            scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w, term_h)
            continue

        # Interactive dropdown selector modal (/menu, /tab, /picker, /models)
        if low in ("/menu", "menu", "/tab", "tab", "/picker", "/select", "/models"):
            init_tab = 0 if low in ("/menu", "menu", "/persona") else 1
            theme, active_workflow_mode = run_dropdown_picker(comp_name, history, initial_tab=init_tab, workflow_mode=active_workflow_mode, user_name=user_name)
            # Re-assert pinned header upon return from dropdown modal
            term_w, term_h = get_term_size()
            scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w, term_h)
            # Print brief 1-line confirmation banner on return
            m_info = get_active_model_info()
            print(f"\n{theme['color']}⚡ Active: {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}] · Model: {m_info['name']} · Mode: {active_workflow_mode}\033[0m\n")
            continue

        if low in ("/mode", "/persona"):
            parts = line.split(maxsplit=1)
            arg = parts[1].strip().lower() if len(parts) > 1 else ""
            if not arg:
                theme, active_workflow_mode = run_dropdown_picker(comp_name, history, initial_tab=0, workflow_mode=active_workflow_mode, user_name=user_name)
                term_w, term_h = get_term_size()
                scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w, term_h)
                continue
            if arg in PERSONA_COMMAND_MAP:
                target_slot = PERSONA_COMMAND_MAP[arg]
                theme, companion_prompt = apply_persona_slot(target_slot, comp_name, active_workflow_mode, user_name)
                history[0] = {"role": "system", "content": companion_prompt}
                refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
                print(f"\n{theme['color']}⚡ Consciousness switched to: {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}] — {theme['preset_name']}\033[0m")
                print(f"{theme['color']}   Focus: {theme['desc']}\033[0m\n")
            else:
                print(f"Unknown persona '{arg}'. Use 1-6 or: companion, friend, beloved, engineer, inventor, assistant.")
            continue

        # Help & Commands Guide
        if low in ("/help", "help", "?", "/?", "/commands", "commands", "/cmd", "cmds"):
            print("\n" + render_commands_help_box(theme, box_w))
            continue

        # Exit / Quit commands
        if low in ("/quit", "/exit", "exit", "quit", ":q", "q", "/q", "back", "/back"):
            print(f"[{comp_name}] Leaving chat. Until next time!")
            break

        # Clear Screen & Reset Context
        if low == "/clear":
            history = [history[0]]
            theme = get_active_persona_theme()
            term_w, term_h = get_term_size()
            sys.stdout.write("\033[r\033[2J\033[H")
            sys.stdout.flush()
            scroll_top = set_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w, term_h)
            sys.stdout.write(f"\033[{scroll_top};1H\n")
            sys.stdout.flush()
            continue

        # --- Direct Workflow Mode Commands (/plan, /code, /plan/code, /normal) ---
        if low in ("/plan", "/planning"):
            active_workflow_mode = "plan"
            tone_b = ""
            try:
                from Backend.Cognition import soul_state
                tone_b = soul_state.build_tone_instructions()
            except Exception:
                pass
            companion_prompt = build_companion_prompt(comp_name, tone_b, active_workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)
            history[0] = {"role": "system", "content": companion_prompt}
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            m_info = CHAT_WORKFLOW_MODES["plan"]
            print(f"\n{theme['color']}📋 Workflow mode switched to: {m_info['name'].upper()} ACTIVE\033[0m")
            print(f"{theme['color']}   Focus: Systematic analysis, architecture check, and numbered milestones.\033[0m\n")
            continue

        if low in ("/code", "/coding", "/dev"):
            active_workflow_mode = "code"
            tone_b = ""
            try:
                from Backend.Cognition import soul_state
                tone_b = soul_state.build_tone_instructions()
            except Exception:
                pass
            companion_prompt = build_companion_prompt(comp_name, tone_b, active_workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)
            history[0] = {"role": "system", "content": companion_prompt}
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            m_info = CHAT_WORKFLOW_MODES["code"]
            print(f"\n{theme['color']}⚡ Workflow mode switched to: {m_info['name'].upper()} ACTIVE\033[0m")
            print(f"{theme['color']}   Focus: Direct, robust code implementations with minimal fluff.\033[0m\n")
            continue

        if low in ("/plan/code", "/code/plan", "/pc", "/cp", "/plan-code", "/code-plan"):
            active_workflow_mode = "plan/code"
            tone_b = ""
            try:
                from Backend.Cognition import soul_state
                tone_b = soul_state.build_tone_instructions()
            except Exception:
                pass
            companion_prompt = build_companion_prompt(comp_name, tone_b, active_workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)
            history[0] = {"role": "system", "content": companion_prompt}
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            m_info = CHAT_WORKFLOW_MODES["plan/code"]
            print(f"\n{theme['color']}🎯 Workflow mode switched to: {m_info['name'].upper()} ACTIVE\033[0m")
            print(f"{theme['color']}   Focus: Concise execution plan first, followed directly by production code.\033[0m\n")
            continue

        if low in ("/chat", "/normal", "/talk", "/reset-mode"):
            active_workflow_mode = "normal"
            tone_b = ""
            try:
                from Backend.Cognition import soul_state
                tone_b = soul_state.build_tone_instructions()
            except Exception:
                pass
            companion_prompt = build_companion_prompt(comp_name, tone_b, active_workflow_mode, CHAT_SETTINGS.get("custom_prompt", ""), user_name)
            history[0] = {"role": "system", "content": companion_prompt}
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            print(f"\n{theme['color']}💬 Workflow mode reset to: Conversational Co-Pilot (Normal)\033[0m\n")
            continue

        # --- Direct Persona Commands (e.g. /friend, /beloved, /engineer, /companion, /inventor, /assistant, /p1 - /p6) ---
        if low in PERSONA_COMMAND_MAP:
            target_slot = PERSONA_COMMAND_MAP[low]
            theme, companion_prompt = apply_persona_slot(target_slot, comp_name, active_workflow_mode, user_name)
            history[0] = {"role": "system", "content": companion_prompt}
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            print(f"\n{theme['color']}⚡ Consciousness switched to: {theme['icon']} [{theme['slot']}] {theme['name']} [{theme['mbti']}] — {theme['preset_name']}\033[0m")
            print(f"{theme['color']}   Focus: {theme['desc']}\033[0m\n")
            continue

        # --- Settings Toggles ---
        if low in ("/thoughts", "/thought", "/monologue"):
            CHAT_SETTINGS["show_thoughts"] = not CHAT_SETTINGS["show_thoughts"]
            st = f"{theme['color']}[ON]\033[0m" if CHAT_SETTINGS["show_thoughts"] else "\033[2m[OFF]\033[0m"
            print(f"\n💭 Internal monologue thoughts: {st}\n")
            continue

        if low in ("/incognito", "/stealth"):
            CHAT_SETTINGS["incognito"] = not CHAT_SETTINGS["incognito"]
            st = f"{theme['color']}[ON]\033[0m" if CHAT_SETTINGS["incognito"] else "\033[2m[OFF]\033[0m"
            print(f"\n🕶️ Incognito mode: {st} (Turns will not be written to memory)\n")
            continue

        if low in ("/super", "/supermemory"):
            CHAT_SETTINGS["super_memory"] = not CHAT_SETTINGS["super_memory"]
            st = f"{theme['color']}[ON]\033[0m" if CHAT_SETTINGS["super_memory"] else "\033[2m[OFF]\033[0m"
            print(f"\n🧠 Super Memory auto-retrieval: {st}\n")
            continue

        # --- Hardware & Model Commands ---
        if low in ("/swap", "/tier b") and load:
            print("⚡ Hot-swapping to Tier B (Qwen3.5-9B-MoQ on VRAM)...")
            res = load("B")
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            print(f"Status: {res}")
            continue

        if low in ("/light", "/tier a") and load:
            print("⚡ Hot-swapping to Tier A (Gemma-4-E2B light)...")
            res = load("A")
            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            print(f"Status: {res}")
            continue

        if low in ("/status", "/mind"):
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
            print(f"{theme['color']}║\033[0m  \033[1mWorkflow Mode\033[0m      : {mode_info['icon']} {mode_info['name']}")
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
        if low.startswith("/model"):
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
                refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
            elif choice == "2" and load:
                print("⚡ Loading Tier A (Gemma-4-E2B light)...")
                load("A")
                refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
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
                            refresh_pinned_header(user_name, comp_name, theme, active_workflow_mode, term_w)
                    except Exception as e:
                        print(f"⚠️ Switch model error: {e}")
            continue

        # /recall command: semantic memory search
        if low.startswith(("/recall", "recall ")):
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

        # Check if prompt asks for deep coding or heavy refactor when auto_tier_b is enabled
        deep_keywords = ["refactor", "complex", "debug", "deep", "architecture", "rewrite", "solve"]
        if CHAT_SETTINGS.get("auto_tier_b") and read_mind and load:
            mind = read_mind()
            cur_tier = mind.get("residency", {}).get("tier")
            if cur_tier != "B" and any(k in low for k in deep_keywords):
                print("⚡ Deep reasoning requested — auto hot-swapping to Flagship Tier B on VRAM...")
                load("B")

        history.append({"role": "user", "content": line})
        chat_turns = [m for m in history if m.get("role") != "system"]
        active_hist = [history[0]] + chat_turns[-16:]

        # Super Memory auto-retrieval
        if CHAT_SETTINGS.get("super_memory") and len(low.split()) >= 4:
            try:
                con = sqlite3.connect(f"file:{FOVEAI_DB}?mode=ro", uri=True, timeout=1)
                q_words = [w for w in low.split() if len(w) > 3]
                if q_words:
                    clause = " OR ".join(["content LIKE ?"] * len(q_words[:4]))
                    params = [f"%{w}%" for w in q_words[:4]]
                    row = con.execute(f"SELECT content FROM agent_memories WHERE ({clause}) ORDER BY id DESC LIMIT 1", params).fetchone()
                    if row and row[0]:
                        active_hist.insert(1, {"role": "system", "content": f"[Super-Memory Context]: {row[0][:400]}"})
                con.close()
            except Exception:
                pass

        sys.stdout.write("Thinking...")
        sys.stdout.flush()
        reply = stream_chat_model(active_hist, max_tokens=4096, speaker_name=comp_name, theme=theme)
        if not reply and load:
            sys.stdout.write("\r\033[K⚡ Waking model into VRAM (loading Flagship Tier B :8408)...\n")
            sys.stdout.flush()
            try:
                load("B")
                reply = stream_chat_model(active_hist, max_tokens=4096, speaker_name=comp_name, theme=theme)
            except Exception as e:
                print(f"⚠️ Failed to auto-wake model: {e}")

        if reply:
            history.append({"role": "assistant", "content": reply})
            # If not in incognito, optionally save turn preview
            if not CHAT_SETTINGS.get("incognito"):
                try:
                    if FOVEAI_DB.exists():
                        con = sqlite3.connect(FOVEAI_DB, timeout=2)
                        con.execute(
                            "INSERT INTO agent_journal (entry, importance, tags, created_at) "
                            "VALUES (?, 1, 'chat,companion', datetime('now'))",
                            (f"[{comp_name} chat · {theme['name']}] Daniel: {line[:120]} | {comp_name}: {reply[:160]}",)
                        )
                        con.commit()
                        con.close()
                except Exception:
                    pass
        else:
            sys.stdout.write("\r\033[K⚠️ No response from model backend. Check 'foveai mind status'.\n")
            sys.stdout.flush()


def main():
    interactive_chat()


if __name__ == "__main__":
    main()
