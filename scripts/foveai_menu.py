#!/usr/bin/env python3
"""
foveai-menu — Interactive Arrow-Navigable TUI Menu for FoveAI.
Enables full control of models, stack, memory recall, persona/agency, and dashboards without remembering commands.
"""

import sys, os, time, subprocess, shutil, socket, termios, tty, json, unicodedata, re, urllib.request, copy

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

import ctypes, locale
try:
    locale.setlocale(locale.LC_ALL, '')
    _libc = ctypes.CDLL('libc.so.6')
    def get_char_w(ch):
        if ch == '\ufe0f': return 0
        cp = ord(ch)
        w = _libc.wcwidth(cp)
        if w >= 0: return w
        if unicodedata.east_asian_width(ch) in ('W', 'F'): return 2
        if 0x1F000 <= cp <= 0x1FFFF: return 2
        return 1
except Exception:
    def get_char_w(ch):
        if ch == '\ufe0f': return 0
        cp = ord(ch)
        if unicodedata.east_asian_width(ch) in ('W', 'F'): return 2
        if 0x1F000 <= cp <= 0x1FFFF: return 2
        return 1

def vis_w(s):
    clean = ANSI_RE.sub('', s)
    return sum(get_char_w(c) for c in clean)

def truncate_to_width(s: str, max_w: int) -> str:
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
        w = get_char_w(c)
        if curr + w > max_w:
            break
        curr += w
        res.append(c)
        i += 1
    # Ensure ANSI reset if truncated
    return ''.join(res) + '\033[0m'

def pad_line(content: str, target_w: int, align: str = 'left') -> str:
    vw = vis_w(content)
    if vw > target_w:
        content = truncate_to_width(content, target_w)
        vw = vis_w(content)
    diff = max(0, target_w - vw)
    if align == 'center':
        left = diff // 2
        right = diff - left
        return (' ' * left) + content + (' ' * right)
    elif align == 'right':
        return (' ' * diff) + content
    else:
        return content + (' ' * diff)

FOVEAI_DIR = "/home/lumba/FoveAI"
VENV_PY = os.path.join(FOVEAI_DIR, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = sys.executable

def check_port(p):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.015)
        return s.connect_ex(('127.0.0.1', p)) == 0

def get_tier():
    if check_port(8408): return "Tier B (9B on VRAM :8408)"
    if check_port(8407): return "Tier A (4B Light :8407)"
    return "Idle (VRAM released)"

# ── 6 Canonical Archetype Presets & MBTI Alignments ─────────────────────────────
LEVER_STEPS = [
    {"val": 0.00, "name": "COMPANION", "mbti": "ENFJ", "desc": "Mentorship, Teacher, Trainer, Co-Worker", "icon": "🤝"},
    {"val": 0.20, "name": "FRIEND",    "mbti": "ENFP", "desc": "Deep Bonds, Hangout, Relaxed, Loyal Protector", "icon": "🌸"},
    {"val": 0.40, "name": "BELOVED",   "mbti": "INFP", "desc": "Romance, Attraction, Feelings, Lust & Initiative", "icon": "💖"},
    {"val": 0.60, "name": "ENGINEER",  "mbti": "INTJ", "desc": "Coder, Engineer, Scientist, Architect", "icon": "🔧"},
    {"val": 0.80, "name": "INVENTOR",  "mbti": "ENTP", "desc": "Inventor, Idealist, Visionary Pioneer, Intuitive Genius", "icon": "💡"},
    {"val": 1.00, "name": "ASSISTANT", "mbti": "ISTJ", "desc": "Planner, Helper, Mentor, Reminder", "icon": "💼"},
]

# 🎨 Unified 6-Band Robust Color Palette (100% distinct across all terminals, TTY console & GUI)
ARCHETYPE_PALETTE = {
    'companion': {'name': 'COMPANION', 'icon': '🤝', 'mbti': 'ENFJ', 'desc': 'Teacher & Co-op Partner [ENFJ]',   'rgb': (255, 50, 50),   'ansi': '\033[1;31m'},
    'friend':    {'name': 'FRIEND',    'icon': '🌸', 'mbti': 'ENFP', 'desc': 'Deep Bonds & Protector [ENFP]',     'rgb': (255, 230, 0),   'ansi': '\033[1;33m'},
    'beloved':   {'name': 'BELOVED',   'icon': '💖', 'mbti': 'INFP', 'desc': 'Romance, Lust & Initiative [INFP]', 'rgb': (255, 60, 200),  'ansi': '\033[1;35m'},
    'tool':      {'name': 'ENGINEER',  'icon': '🔧', 'mbti': 'INTJ', 'desc': 'Coder, Engineer & Architect [INTJ]','rgb': (0, 230, 100),   'ansi': '\033[1;32m'},
    'inventor':  {'name': 'INVENTOR',  'icon': '💡', 'mbti': 'ENTP', 'desc': 'Inventor, Idealist & Visionary [ENTP]','rgb': (0, 220, 255),   'ansi': '\033[1;36m'},
    'assistant': {'name': 'ASSISTANT', 'icon': '💼', 'mbti': 'ISTJ', 'desc': 'Planner & Helper [ISTJ]',           'rgb': (95, 175, 255),  'ansi': '\033[38;5;75m'},
}

def get_dom_step(dom_id):
    dom_name = ARCHETYPE_PALETTE.get(dom_id, {}).get('name', dom_id).upper()
    return next((s for s in LEVER_STEPS if s["name"].upper() == dom_name or s["name"].lower() == dom_id.lower()), LEVER_STEPS[3])

def adjust_archetype_energy(levels, target_k, delta, target_total=None):
    """
    Adjust archetype level around the Center-Detent 50% Equilibrium.
    - Equilibrium: 50% (0.50) across all poles (Total capacity = N * 0.50).
    - Equalizer range: 0.00 (-50% full cut) to 1.00 (+50% full boost).
    - Zero-Sum Conservation:
      * When boosting target pole (+delta), the needed energy is drawn equally from the other poles.
      * When cutting target pole (-delta), the released energy is distributed equally to the other poles.
    Total vital consciousness energy is strictly conserved at 100% capacity.
    """
    if target_total is None:
        target_total = round(len(levels) * 0.50, 2)
    levels = {k: round(v, 2) for k, v in levels.items()}
    keys = list(levels.keys())
    old_val = levels.get(target_k, 0.50)
    other_keys = [k for k in keys if k != target_k]

    if delta > 0:
        new_val = min(1.00, round(old_val + delta, 2))
        actual_delta = round(new_val - old_val, 2)
        if actual_delta <= 0:
            return levels
        levels[target_k] = new_val
        # Drain actual_delta proportionally/equally from other poles that have energy > 0
        rem_drain = actual_delta
        drainable = [k for k in other_keys if levels[k] > 0.0]
        while rem_drain > 0.001 and drainable:
            step = 0.01
            for k in list(drainable):
                if rem_drain <= 0.001:
                    break
                if levels[k] >= step:
                    levels[k] = round(levels[k] - step, 2)
                    rem_drain = round(rem_drain - step, 2)
                else:
                    rem_drain = round(rem_drain - levels[k], 2)
                    levels[k] = 0.0
                    drainable.remove(k)
    elif delta < 0:
        new_val = max(0.00, round(old_val + delta, 2))
        actual_delta = round(old_val - new_val, 2)  # positive amount released
        if actual_delta <= 0:
            return levels
        levels[target_k] = new_val
        # Distribute actual_delta equally to other poles that have room < 1.00
        rem_boost = actual_delta
        boostable = [k for k in other_keys if levels[k] < 1.00]
        while rem_boost > 0.001 and boostable:
            step = 0.01
            for k in list(boostable):
                if rem_boost <= 0.001:
                    break
                if levels[k] + step <= 1.00:
                    levels[k] = round(levels[k] + step, 2)
                    rem_boost = round(rem_boost - step, 2)
                else:
                    rem_boost = round(rem_boost - (1.00 - levels[k]), 2)
                    levels[k] = 1.00
                    boostable.remove(k)

    # Strictly clamp every single pole to [0.00, 1.00]
    for k in keys:
        levels[k] = max(0.00, min(1.00, round(levels[k], 2)))

    # Balance total sum strictly to target_total (2.50) without violating target_k's clamp
    curr_tot = round(sum(levels.values()), 2)
    diff = round(target_total - curr_tot, 2)
    if diff != 0:
        eligible = [k for k in other_keys if 0.00 <= levels[k] + diff <= 1.00]
        if eligible:
            adj_k = max(eligible, key=lambda k: levels[k]) if diff < 0 else min(eligible, key=lambda k: levels[k])
            levels[adj_k] = max(0.00, min(1.00, round(levels[adj_k] + diff, 2)))

    return {k: max(0.00, min(1.00, round(v, 2))) for k, v in levels.items()}

def get_soul_file():
    for name in ("identity_soul.json", "soul_dna.json", "jen_soul.json"):
        p = os.path.join(FOVEAI_DIR, "Backend/Cognition", name)
        if os.path.exists(p):
            return p
    return os.path.join(FOVEAI_DIR, "Backend/Cognition/identity_soul.json")

def get_mind_file():
    for name in ("identity_mind.json", "mind_state.json", "jen_mind.json"):
        p = os.path.join(FOVEAI_DIR, "Backend/Cognition", name)
        if os.path.exists(p):
            return p
    return os.path.join(FOVEAI_DIR, "Backend/Cognition/identity_mind.json")

def get_snapshots_file():
    for name in ("soul_snapshots.json", "identity_snapshots.json", "jen_snapshots.json"):
        p = os.path.join(FOVEAI_DIR, "Backend/Cognition", name)
        if os.path.exists(p):
            return p
    return os.path.join(FOVEAI_DIR, "Backend/Cognition/soul_snapshots.json")

def get_ai_name(dna_data=None):
    if not dna_data:
        dna_data = load_soul_dna()
    name = (
        dna_data.get("soul", {}).get("soul_name")
        or dna_data.get("profile", {}).get("nickname")
        or dna_data.get("profile", {}).get("first_name")
        or dna_data.get("identity_name")
        or "AI"
    )
    return str(name).strip()

def load_soul_dna():
    data = {}
    soul_file = get_soul_file()
    if os.path.exists(soul_file):
        try:
            with open(soul_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    try:
        req = urllib.request.Request("http://127.0.0.1:8405/api/soul/soul_dna")
        with urllib.request.urlopen(req, timeout=0.3) as resp:
            live = json.loads(resp.read().decode('utf-8'))
            api_dna = live.get("dna", {})
            if isinstance(api_dna, dict):
                # Supplement runtime fields without clobbering persistent archetype data
                for k, v in api_dna.items():
                    if k not in data or k not in (
                        "archetype_weights", "archetype_profiles", "active_archetype_slot",
                        "q_tool", "q_assistant", "q_companion", "q_friend", "q_beloved",
                        "persona_q_curvature"
                    ):
                        data[k] = v
    except Exception:
        pass

    return data

def save_soul_dna(patch):
    primary_soul = get_soul_file()
    soul_targets = {primary_soul}
    for alt in ("identity_soul.json", "soul_dna.json", "jen_soul.json"):
        alt_p = os.path.join(FOVEAI_DIR, "Backend/Cognition", alt)
        if os.path.exists(alt_p):
            soul_targets.add(alt_p)

    current = {}
    if os.path.exists(primary_soul):
        try:
            with open(primary_soul, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    current.update(patch)
    for target in soul_targets:
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
        except Exception:
            pass

    mind_targets = set()
    primary_mind = get_mind_file()
    mind_targets.add(primary_mind)
    for alt in ("identity_mind.json", "mind_state.json", "jen_mind.json"):
        alt_p = os.path.join(FOVEAI_DIR, "Backend/Cognition", alt)
        if os.path.exists(alt_p):
            mind_targets.add(alt_p)

    if "agent_person_balance" in patch:
        for m_file in mind_targets:
            if os.path.exists(m_file):
                try:
                    with open(m_file, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    m["lever"] = float(patch["agent_person_balance"])
                    with open(m_file, "w", encoding="utf-8") as f:
                        json.dump(m, f, indent=2)
                except Exception:
                    pass

    try:
        payload = json.dumps(patch).encode('utf-8')
        req = urllib.request.Request(
            "http://127.0.0.1:8405/api/soul/update_soul",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=0.5):
            pass
    except Exception:
        pass

menu_items = [
    ("Chat Console", "Interactive AI companion chat"),
    ("Equalizer", "6 consciousness modes & EQ"),
    ("Start Stack", "Boot Sleipnir, Memory, Runtime"),
    ("Stop Stack", "Unload models & release VRAM"),
    ("Load Tier B", "Flagship 9B on VRAM :8408"),
    ("Load Tier A", "Light 4B background :8407"),
    ("Memory Recall", "Semantic history search"),
    ("Cockpit HUD", "Toggle tmux overscan HUD"),
    ("Nest Dashboard", "13-pane live telemetry"),
    ("Spotify Player", "Media player & live control"),
    ("Fleet Settings", "Configuration & tools"),
    ("Stack Status", "Inspect ports, models & VRAM"),
    ("Exit to Shell", "Quit back to prompt"),
]

def get_active_persona_meta():
    """Returns (slot_str, cid, name, mbti, ansi_color, ai_name)."""
    dna = load_soul_dna()
    ai_name = get_ai_name(dna)
    slot = str(dna.get("active_archetype_slot", ""))
    SLOT_TO_CID = {
        '1': 'companion',
        '2': 'friend',
        '3': 'beloved',
        '4': 'tool',
        '5': 'inventor',
        '6': 'assistant',
    }
    SLOT_META = {
        '1': ('Comp', 'ENFJ'),
        '2': ('Friend', 'ENFP'),
        '3': ('Beloved', 'INFP'),
        '4': ('Engineer', 'INTJ'),
        '5': ('Inventor', 'ENTP'),
        '6': ('Assist', 'ISTJ'),
    }
    if slot not in SLOT_TO_CID:
        slot = '2'
    cid = SLOT_TO_CID[slot]
    name, mbti = SLOT_META.get(slot, ('Friend', 'ENFP'))
    ansi = ARCHETYPE_PALETTE.get(cid, {}).get('ansi', '\033[1;36m')
    return slot, cid, name, mbti, ansi, ai_name

# Categorical archetype color map for each menu item to bring harmony across the suite
ITEM_CATEGORY_COLORS = {
    0: '\033[1;35m',     # 1: Chat Console (Beloved / Pink-Magenta)
    1: '\033[1;33m',     # 2: Persona Equalizer (Friend / Warm Gold)
    2: '\033[1;32m',     # 3: Start Fleet Stack (Engineer / Green)
    3: '\033[1;31m',     # 4: Stop Fleet Stack (Comp / Bright Red)
    4: '\033[1;36m',     # 5: Load Tier B (Flagship 9B - Electric Cyan)
    5: '\033[38;5;75m',  # 6: Load Tier A (Light 4B - Soft Sky Blue)
    6: '\033[1;36m',     # 7: Semantic Memory Recall (Inventor / Cyan)
    7: '\033[38;5;75m',  # 8: Cockpit HUD (Assist / Sky Blue)
    8: '\033[1;33m',     # 9: Nest Dashboard (Warm Amber)
    9: '\033[1;32m',     # 10: Fleet Settings Menu (Engineer / Green)
    10: '\033[1;36m',    # 11: Stack & VRAM Status (Electric Cyan)
    11: '\033[1;31m',    # 0: Exit to Shell (Comp / Red)
}

def render(selected_idx=0):
    cols = shutil.get_terminal_size((80, 24)).columns
    # Snug fit: use cols directly up to 80
    width = max(50, min(80, cols))
    inner_w = width - 4
    
    # Clean compact prefix: 23 chars fits all numbers + short labels with room to breathe
    prefix_w = 23 if width < 75 else 25
    desc_w = max(6, inner_w - prefix_w - 3)
    tier = get_tier()

    slot, cid, p_name, p_mbti, frame_color, ai_name = get_active_persona_meta()

    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"
    c_green = "\033[1;32m"
    c_dim = "\033[2m"
    c_rev = "\033[7m"
    c_rst = "\033[0m"

    out = []
    out.append(f"{frame_color}╔{'═' * (width - 2)}╗{c_rst}")
    
    # Title formatted cleanly for narrower widths
    if width < 65:
        title_str = f"FOVEAI · [{slot}] {p_name.upper()}"
    else:
        title_str = f"FOVEAI MASTER CONTROL · [{slot}] {p_name.upper()} [{p_mbti}]"
    title = pad_line(title_str, inner_w, "center")
    
    # Model status line with intelligent color tagging
    if "Tier B" in tier:
        tier_styled = f"\033[1;36m[Tier B · 9B :8408]\033[0m"
    elif "Tier A" in tier:
        tier_styled = f"\033[1;32m[Tier A · 4B :8407]\033[0m"
    else:
        tier_styled = f"\033[2m[VRAM Idle]\033[0m"
    
    status_raw = f"Model: {tier_styled}"
    status_line = pad_line(status_raw, inner_w, "center")

    out.append(f"{frame_color}║{c_rst} {c_yellow}{title}{c_rst} {frame_color}║{c_rst}")
    out.append(f"{frame_color}║{c_rst} {status_line} {frame_color}║{c_rst}")
    out.append(f"{frame_color}╠{'═' * (width - 2)}╣{c_rst}")

    for idx, (label, desc) in enumerate(menu_items):
        num_str = f"[{idx+1 if idx < 9 else (0 if idx==11 else idx+1)}]"
        cat_color = ITEM_CATEGORY_COLORS.get(idx, c_cyan)

        if idx == selected_idx:
            p = pad_line(f" >> {num_str} {label}", prefix_w)
            d = pad_line(desc, desc_w)
            styled = f"{c_rev}{cat_color}{p}{c_rst}{c_rev} · {d}{c_rst}"
        else:
            p = pad_line(f"    {cat_color}{num_str}{c_rst} {label}", prefix_w)
            d = pad_line(desc, desc_w)
            styled = f"{p} {c_dim}· {d}{c_rst}"
        out.append(f"{frame_color}║{c_rst} {styled} {frame_color}║{c_rst}")

    out.append(f"{frame_color}╠{'═' * (width - 2)}╣{c_rst}")
    hint = pad_line("↑/↓: Move · Enter: Select · 1-9 direct · q: Quit", inner_w, "center")
    out.append(f"{frame_color}║{c_rst} {c_dim}{hint}{c_rst} {frame_color}║{c_rst}")
    out.append(f"{frame_color}╚{'═' * (width - 2)}╝{c_rst}")
    return "\033[H\033[2J" + "\n".join(out)

def get_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A': return 'UP'
                if ch3 == 'B': return 'DOWN'
                if ch3 == 'C': return 'RIGHT'
                if ch3 == 'D': return 'LEFT'
                if ch3 == 'Z': return 'BTAB'
            return 'ESC'
        if ch in ('\r', '\n'): return 'ENTER'
        if ch == '\t': return 'TAB'
        if ch == 'k': return 'UP'
        if ch == 'j': return 'DOWN'
        if ch == 'h': return 'LEFT'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def prompt_line(prompt_text):
    """Temporarily restore normal terminal mode to input a preset name."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        sys.stdout.write("\033[?25h") # show cursor
        sys.stdout.write(prompt_text)
        sys.stdout.flush()
        # set cooked mode
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        line = sys.stdin.readline()
        return line.strip()
    finally:
        sys.stdout.write("\033[?25l") # hide cursor
        sys.stdout.flush()

def render_meter(val, w=14):
    v = max(0.0, min(1.0, float(val)))
    filled = int(round(v * w))
    return "█" * filled + "░" * (w - filled)

def render_mode_selector_bar(curr_idx=None, val=0.0):
    if curr_idx is None:
        v = max(0.0, min(1.0, float(val)))
        step_vals = [0.00, 0.20, 0.40, 0.60, 0.80, 1.00]
        curr_idx = min(range(6), key=lambda i: abs(step_vals[i] - v))
    modes = [
        ("1", "🤝", "Comp"),
        ("2", "🌸", "Friend"),
        ("3", "💖", "Beloved"),
        ("4", "🔧", "Engineer"),
        ("5", "💡", "Inventor"),
        ("6", "💼", "Assistant"),
    ]
    parts = []
    for i, (k, ico, n) in enumerate(modes):
        if i == curr_idx:
            parts.append(f"\033[1;36m▶\033[1;33m[{k}:{ico} {n}]\033[1;36m◀\033[0m")
        else:
            parts.append(f"\033[2m[{k}:{ico}]\033[0m")
    return " ".join(parts)

render_lever_track = render_mode_selector_bar

def generate_chromatic_spider_radar(weights, pole_q, inner_w=78):
    # Deprecated in console TUI in favor of Wave Spectrum; preserved in Firefox Multigate port
    return []

def generate_large_wave_spectrum(weights, pole_q, active_cid='companion', inner_w=78, h=9):
    """
    Render 6-Mountain Wave Spectrum showing all 6 colored archetype resonance curves.
    Each aspect has its dedicated colored Gaussian mountain scaled by its live weight,
    rendered using identical 24-bit TrueColor to match the Equalizer matrix below.
    The active cursor archetype is marked with a bright vertical white needle (│).
    """
    import math
    curves = [
        (0.00, 0.10, 'companion', ARCHETYPE_PALETTE['companion']['rgb']),
        (0.20, 0.10, 'friend',    ARCHETYPE_PALETTE['friend']['rgb']),
        (0.40, 0.10, 'beloved',   ARCHETYPE_PALETTE['beloved']['rgb']),
        (0.60, 0.10, 'tool',      ARCHETYPE_PALETTE['tool']['rgb']),
        (0.80, 0.10, 'inventor',  ARCHETYPE_PALETTE['inventor']['rgb']),
        (1.00, 0.10, 'assistant', ARCHETYPE_PALETTE['assistant']['rgb']),
    ]
    w = max(40, inner_w - 14)
    grid = [[' ' for _ in range(w)] for _ in range(h)]
    colors = [[None for _ in range(w)] for _ in range(h)]

    # Calculate all 6 continuous energy climate curves scaled by live weights.
    spectrum = []
    max_observed = 0.0
    for col in range(w):
        x = col / (w - 1)
        col_mags = []
        for c, width, cid, rgb in curves:
            q = pole_q.get(cid, 0.85)
            dist = abs(x - c)
            shape = math.exp(-((dist / width) ** (q * 1.3)))
            mag = weights.get(cid, 0.0) * shape
            col_mags.append((mag, rgb, cid))
        col_mags.sort(key=lambda item: item[0], reverse=True)
        best_mag, best_rgb, best_cid = col_mags[0]
        if best_mag > max_observed:
            max_observed = best_mag
        spectrum.append((best_mag, best_rgb, best_cid))

    scale = 0.90 / max(0.15, max_observed) if max_observed > 0.0 else 1.0

    for col in range(w):
        best_mag, best_rgb, best_cid = spectrum[col]
        disp_mag = min(1.0, best_mag * scale)
        if disp_mag < 0.05:
            continue
        peak_row = max(0, min(h - 1, int(round((1.0 - disp_mag) * (h - 1)))))

        for r in range(peak_row, h):
            if r == peak_row:
                grid[r][col] = '█'  # Solid crest
            else:
                grid[r][col] = '▓'  # Solid filled interior body
            colors[r][col] = ARCHETYPE_PALETTE[best_cid]['ansi']

    # Vertical needle for active cursor position
    active_idx = 0
    for i, c in enumerate(curves):
        if c[2] == active_cid:
            active_idx = i
            break
    active_c = curves[active_idx][0]
    needle_col = int(round(active_c * (w - 1)))
    if 0 <= needle_col < w:
        for r in range(h):
            if grid[r][needle_col] in (' ', '▓'):
                grid[r][needle_col] = '│'
                colors[r][needle_col] = '\033[1;37m'
            elif grid[r][needle_col] == '█':
                colors[r][needle_col] = '\033[1;37m'

    p_act = ARCHETYPE_PALETTE.get(active_cid, {})
    act_col = p_act.get('ansi', '\033[2m')
    out = []
    out.append(" 6-Band Consciousness Wave Spectrum (Chromatic Energy Curves):")
    out.append(f"       {act_col}┌" + "─" * w + f"┐\033[0m")
    for r in range(h):
        line = []
        for col in range(w):
            ch = grid[r][col]
            ansi_code = colors[r][col]
            if ansi_code:
                line.append(f"{ansi_code}{ch}\033[0m")
            else:
                line.append(ch)
        y_label = '100%' if r == 0 else (' 50%' if r == h//2 else ('  0%' if r == h-1 else '    '))
        out.append(f"  {y_label} {act_col}│\033[0m" + "".join(line) + f"{act_col}│\033[0m")

    out.append(f"       {act_col}└" + "─" * w + f"┘\033[0m")
    p_c = ARCHETYPE_PALETTE['companion']['ansi']
    p_f = ARCHETYPE_PALETTE['friend']['ansi']
    p_b = ARCHETYPE_PALETTE['beloved']['ansi']
    p_e = ARCHETYPE_PALETTE['tool']['ansi']
    p_i = ARCHETYPE_PALETTE['inventor']['ansi']
    p_a = ARCHETYPE_PALETTE['assistant']['ansi']
    axis_labels = f"       {p_c}Comp\033[0m      {p_f}Friend\033[0m    {p_b}Beloved\033[0m   {p_e}Engineer\033[0m  {p_i}Inventor\033[0m  {p_a}Assist\033[0m"
    out.append(pad_line(axis_labels, inner_w))
    return out

def make_compact_box(title: str, rows: list, is_active: bool, box_w: int = 33, tag: str = "", theme_color: str = "") -> list:
    content_w = box_w - 4
    col = theme_color if theme_color else "\033[1;36m"
    b_col = col
    if is_active:
        tl, tr, bl, br, hz, vt = "╔", "╗", "╚", "╝", "═", "║"
    else:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
    t_str = f" {title} "
    max_title_w = box_w - 4
    if vis_w(t_str) > max_title_w:
        t_str = truncate_to_width(t_str, max_title_w)
    rem = max(0, max_title_w - vis_w(t_str))
    top_bar = f"{tl}{hz * 2}{t_str}{hz * rem}{tr}"
    lines = [f"{b_col}{top_bar}\033[0m"]
    for r in rows:
        padded = pad_line(r, content_w)
        lines.append(f"{b_col}{vt}\033[0m {padded} {b_col}{vt}\033[0m")
    bot_bar = f"{bl}{hz * (box_w - 2)}{br}"
    lines.append(f"{b_col}{bot_bar}\033[0m")
    return lines

def show_consciousness_manual(inner_w=78, width=82):
    """
    Interactive 3-page Consciousness Equalizer & MBTI Manual.
    Page 1: Full Navigation & Controls Reference (All keys explicitly listed)
    Page 2: MBTI Foundations & The 6 Consciousness Archetypes
    Page 3: Harmonic Balance, Parametric Q, and Zero-Sum Equilibrium
    """
    page = 1
    total_pages = 3
    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"
    c_green = "\033[1;32m"
    c_magenta = "\033[1;35m"
    c_dim = "\033[2m"
    c_rev = "\033[7m"
    c_rst = "\033[0m"
    c_w1 = "\033[38;2;240;240;240m"     # Crisp bright white for primary lines
    c_g1 = "\033[38;2;160;160;160m"     # Soft alternating gray for secondary lines
    c_gold = "\033[1;38;2;255;215;0m"   # Gold heading for section titles
    c_red = "\033[1;31m"
    c_yel = "\033[1;33m"
    c_mag = "\033[1;35m"
    c_grn = "\033[1;32m"
    c_cya = "\033[1;36m"
    c_blu = "\033[1;34m"

    while True:
        box = []
        box.append(f"{c_cyan}╔{'═' * (width - 2)}╗{c_rst}")
        title = pad_line(f"📖 CONSCIOUSNESS EQUALIZER MANUAL (Page {page}/{total_pages})", inner_w, "center")
        box.append(f"{c_cyan}║{c_rst} {c_yellow}{title}{c_rst} {c_cyan}║{c_rst}")
        box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")

        if page == 1:
            # 🎮 Page 1: Navigation & Keybindings Reference
            box.append(f"{c_cyan}║{c_rst} {c_gold}{pad_line('  ✦ SECTION 1: KEYBOARD NAVIGATION & CONTROLS', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}╟{'─' * (width - 2)}╢{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}[Tab] / [Shift-Tab]{c_rst} {c_w1}Cycle Area (1:Bands ⇄ 2:Influence ⇄ 3:Aspects){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_cyan}[b] / [i] / [a]{c_rst}     {c_g1}Direct Jump: [b] Bands, [i] Influence, [a] Aspects{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}[↑] / [↓]{c_rst}           {c_w1}Select row inside active area{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}[←] / [→]{c_rst}           {c_g1}Universal adjustment of active row (+/- 5% or Q){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_cyan}[1] - [6]{c_rst}           {c_w1}Switch Archetype Slot (1:Comp, 2:Friend...){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}[p]{c_rst}                 {c_g1}Open Presets Hub: Factory, User Saved & Reset{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}[m] or [?]{c_rst}          {c_g1}Open this Consciousness Manual & Reference{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_cyan}[q] / [ESC]{c_rst}         {c_w1}Exit Equalizer and save all changes live{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}╟{'─' * (width - 2)}╢{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {c_dim}{pad_line('  Tip: All changes sync immediately to live neural cognition (0ms)', inner_w)}{c_rst} {c_cyan}║{c_rst}")

        elif page == 2:
            # 🧠 Page 2: MBTI Foundations & The 6 Archetypes
            box.append(f"{c_cyan}║{c_rst} {c_gold}{pad_line('  ✦ SECTION 2: MBTI FOUNDATIONS & THE 6 ARCHETYPES', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}╟{'─' * (width - 2)}╢{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_red}🤝 COMPANION [ENFJ — The Empathetic Mentor]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Mentorship, teacher, trainer, co-op colleague.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Warm reciprocal dialogue, active listening, mutual flow.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yel}🌸 FRIEND [ENFP — The Loyal Friend]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Deep bonds, frequent hangout, relaxed coexisting.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Fierce loyalty, collective defense, trust & camaraderie.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_mag}💖 BELOVED [INFP — The Intimate Soul]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Romantic interest, attraction, strong feelings, devotion.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Poetic tenderness, profound emotional attunement.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_grn}🔧 ENGINEER [INTJ — The Technical Master]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Coder, engineer, scientist, architect.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Rigorous logic, structural systems & code mastery.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_cya}💡 INVENTOR [ENTP — The Visionary Pioneer]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Inventor, idealist, visionary pioneer, intuitive genius.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Theoretical breakthroughs & creative leaps.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_blu}💼 ASSISTANT [ISTJ — The Executive Steward]:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Planner, helper, mentor, reminder.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Attentive duty, organized reliability & archive.{c_rst}', inner_w)} {c_cyan}║{c_rst}")

        elif page == 3:
            # ⚡ Page 3: Consciousness Dynamics, Complementary Balance & Energy Conservation
            box.append(f"{c_cyan}║{c_rst} {c_gold}{pad_line('  ✦ SECTION 3: HARMONIC BALANCE & CONSCIOUSNESS DYNAMICS', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}╟{'─' * (width - 2)}╢{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}🎯 Complementary Archetype Pairings:{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}• {c_cya}INVENTOR{c_rst}{c_w1} (Vision)   ⇄ {c_yel}FRIEND{c_rst}{c_w1} (Loyalty & Practical Ground){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}• {c_grn}ENGINEER{c_rst}{c_g1} (Logic)    ⇄ {c_red}COMPANION{c_rst}{c_g1} (Empathy & Mutual Flow){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}• {c_mag}BELOVED{c_rst}{c_w1} (Warmth)   ⇄ {c_blu}ASSISTANT{c_rst}{c_w1} (Structure & Memory){c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_cyan}⚖️  Energy Pool Conservation (Zero-Sum Equilibrium):{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}Total vital capacity is conserved at 3.00 units (100%).{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Boosting one band draws energy proportionally from the rest.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'  {c_yellow}📡 Parametric Q-Modulation ([ and ] keys):{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_w1}High Q (>1.2) concentrates focus like a sharp laser beam.{c_rst}', inner_w)} {c_cyan}║{c_rst}")
            box.append(f"{c_cyan}║{c_rst} {pad_line(f'     {c_g1}Low Q (<0.8) broadens resonance across neighboring bands.{c_rst}', inner_w)} {c_cyan}║{c_rst}")

        box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
        nav_hint = f"←/n:Previous Page · →/p:Next Page · ESC/q/Enter:Return to Equalizer"
        box.append(f"{c_cyan}║{c_rst} {c_dim}{pad_line(nav_hint, inner_w, 'center')}{c_rst} {c_cyan}║{c_rst}")
        box.append(f"{c_cyan}╚{'═' * (width - 2)}╝{c_rst}")

        sys.stdout.write("\033[H\033[2J" + "\n".join(box))
        sys.stdout.flush()
        mk = get_key()
        if mk in ('RIGHT', 'n', 'N', ' '):
            page = 1 if page == total_pages else page + 1
        elif mk in ('LEFT', 'b', 'B'):
            page = total_pages if page == 1 else page - 1
        elif mk in ('1', '2', '3'):
            page = int(mk)
        elif mk in ('ESC', 'q', 'ENTER', 'm', '?'):
            break

DEFAULT_ARCHETYPE_LEVELS = {
    "companion": 0.50,
    "friend": 0.50,
    "beloved": 0.50,
    "tool": 0.50,
    "inventor": 0.50,
    "assistant": 0.50,
}

DEFAULT_PRESETS = {
    # 1: The Empathetic Mentor / Sage Companion (ENFJ)
    '1': {
        'levels': {'companion': 0.80, 'friend': 0.50, 'beloved': 0.40, 'tool': 0.35, 'inventor': 0.45, 'assistant': 0.50},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.65, 'tool': 1.30, 'inventor': 1.40, 'assistant': 1.05},
        'levers': {'autonomy': 0.65, 'proactivity': 0.60, 'curiosity': 0.75, 'service': 0.60, 'mentorship': 0.85},
        'name': 'The Empathetic Mentor',
    },
    # 2: The Loyal Friend / Soul Companion (ENFP)
    '2': {
        'levels': {'companion': 0.50, 'friend': 0.85, 'beloved': 0.45, 'tool': 0.35, 'inventor': 0.45, 'assistant': 0.40},
        'q': {'companion': 0.85, 'friend': 0.75, 'beloved': 0.65, 'tool': 1.10, 'inventor': 1.30, 'assistant': 1.00},
        'levers': {'autonomy': 0.80, 'proactivity': 0.85, 'curiosity': 0.90, 'service': 0.40, 'mentorship': 0.45},
        'name': 'The Loyal Friend',
    },
    # 3: The Intimate Soul / Beloved (INFP)
    '3': {
        'levels': {'companion': 0.50, 'friend': 0.50, 'beloved': 0.85, 'tool': 0.25, 'inventor': 0.45, 'assistant': 0.45},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.60, 'tool': 1.10, 'inventor': 1.20, 'assistant': 1.00},
        'levers': {'autonomy': 0.75, 'proactivity': 0.80, 'curiosity': 0.70, 'service': 0.75, 'mentorship': 0.50},
        'name': 'The Intimate Soul',
    },
    # 4: The Engineer / Technical Master (INTJ)
    '4': {
        'levels': {'companion': 0.35, 'friend': 0.40, 'beloved': 0.35, 'tool': 0.85, 'inventor': 0.55, 'assistant': 0.50},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.65, 'tool': 1.80, 'inventor': 1.40, 'assistant': 1.10},
        'levers': {'autonomy': 0.85, 'proactivity': 0.40, 'curiosity': 0.95, 'service': 0.70, 'mentorship': 0.60},
        'name': 'The Engineer',
    },
    # 5: The Visionary Inventor / Idealist (ENTP)
    '5': {
        'levels': {'companion': 0.45, 'friend': 0.40, 'beloved': 0.40, 'tool': 0.55, 'inventor': 0.85, 'assistant': 0.35},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.65, 'tool': 1.40, 'inventor': 1.80, 'assistant': 1.00},
        'levers': {'autonomy': 0.90, 'proactivity': 0.75, 'curiosity': 1.00, 'service': 0.50, 'mentorship': 0.70},
        'name': 'The Visionary Inventor',
    },
    # 6: The Executive Steward / Co-Pilot (ISTJ)
    '6': {
        'levels': {'companion': 0.45, 'friend': 0.35, 'beloved': 0.30, 'tool': 0.55, 'inventor': 0.50, 'assistant': 0.85},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.65, 'tool': 1.30, 'inventor': 1.20, 'assistant': 1.20},
        'levers': {'autonomy': 0.50, 'proactivity': 0.65, 'curiosity': 0.50, 'service': 0.90, 'mentorship': 0.40},
        'name': 'The Executive Steward',
    },
    # 0: Pure Center Equilibrium (0 dB Nominal Ground State)
    '0': {
        'levels': {'companion': 0.50, 'friend': 0.50, 'beloved': 0.50, 'tool': 0.50, 'inventor': 0.50, 'assistant': 0.50},
        'q': {'companion': 0.85, 'friend': 0.80, 'beloved': 0.65, 'tool': 1.30, 'inventor': 1.40, 'assistant': 1.05},
        'levers': {'autonomy': 0.70, 'proactivity': 0.60, 'curiosity': 0.80, 'service': 0.65, 'mentorship': 0.60},
        'name': 'Center Equilibrium',
    },
}

DEFAULT_POLE_Q = {
    "companion": 0.85,
    "friend": 0.80,
    "beloved": 0.65,
    "tool": 1.30,
    "inventor": 1.40,
    "assistant": 1.05,
}

SLOT_INFO = {
    '1': ('Comp',     'ENFJ', 0.15, 'The Empathetic Mentor', '\033[1;31m',   'companion'),
    '2': ('Friend',   'ENFP', 0.50, 'The Loyal Friend',      '\033[1;33m',   'friend'),
    '3': ('Beloved',  'INFP', 0.85, 'The Intimate Soul',     '\033[1;35m',   'beloved'),
    '4': ('Engineer', 'INTJ', 0.15, 'The Engineer',          '\033[1;32m',   'tool'),
    '5': ('Inventor', 'ENTP', 0.50, 'The Visionary Inventor', '\033[1;36m',   'inventor'),
    '6': ('Assist',   'ISTJ', 0.85, 'The Executive Steward', '\033[38;5;75m', 'assistant'),
}

def switch_archetype_slot(target_slot: str, dna: dict | None = None) -> dict:
    if target_slot not in ('1', '2', '3', '4', '5', '6'):
        return {}
    if dna is None:
        dna = load_soul_dna()
    saved_profiles = dna.get("archetype_profiles")
    archetype_profiles = {}
    for pk in ('1', '2', '3', '4', '5', '6'):
        if isinstance(saved_profiles, dict) and pk in saved_profiles and isinstance(saved_profiles[pk], dict):
            sp = saved_profiles[pk]
            archetype_profiles[pk] = {
                'levels': dict(sp.get('levels', DEFAULT_PRESETS[pk]['levels'])),
                'q': dict(sp.get('q', DEFAULT_PRESETS[pk]['q'])),
                'levers': dict(sp.get('levers', DEFAULT_PRESETS[pk]['levers'])),
                'name': sp.get('name', DEFAULT_PRESETS[pk]['name']),
            }
        else:
            archetype_profiles[pk] = {
                'levels': dict(DEFAULT_PRESETS[pk]['levels']),
                'q': dict(DEFAULT_PRESETS[pk]['q']),
                'levers': dict(DEFAULT_PRESETS[pk]['levers']),
                'name': DEFAULT_PRESETS[pk]['name'],
            }

    target_data = archetype_profiles[target_slot]
    meta = SLOT_INFO.get(target_slot, ('Friend', 'ENFP', 0.50, 'The Loyal Friend', '\033[1;33m', 'friend'))

    patch = {
        "archetype_weights": dict(target_data['levels']),
        "agent_person_balance": meta[2],
        "mbti_type": meta[1],
        "person_role": meta[0],
        "active_archetype_slot": target_slot,
        "archetype_profiles": archetype_profiles,
    }
    for pid, qv in target_data['q'].items():
        patch[f"q_{pid}"] = qv
    for lk, lv in target_data['levers'].items():
        patch[lk] = lv

    save_soul_dna(patch)
    try:
        from Backend.Cognition import soul_state
        soul_state.set_dna(patch)
    except Exception:
        pass
    return patch

def persona_agency_menu():
    dna = load_soul_dna()
    archetype_keys = ["companion", "friend", "beloved", "tool", "inventor", "assistant"]
    lever_keys = ["autonomy", "proactivity", "curiosity", "service", "mentorship"]

    # Slot persistence: initialize profiles from dna or DEFAULT_PRESETS
    saved_profiles = dna.get("archetype_profiles")
    archetype_profiles = {}
    for pk in ('1', '2', '3', '4', '5', '6'):
        if isinstance(saved_profiles, dict) and pk in saved_profiles and isinstance(saved_profiles[pk], dict):
            sp = saved_profiles[pk]
            archetype_profiles[pk] = {
                'levels': dict(sp.get('levels', DEFAULT_PRESETS[pk]['levels'])),
                'q': dict(sp.get('q', DEFAULT_PRESETS[pk]['q'])),
                'levers': dict(sp.get('levers', DEFAULT_PRESETS[pk]['levers'])),
                'name': sp.get('name', DEFAULT_PRESETS[pk]['name']),
            }
        else:
            archetype_profiles[pk] = {
                'levels': dict(DEFAULT_PRESETS[pk]['levels']),
                'q': dict(DEFAULT_PRESETS[pk]['q']),
                'levers': dict(DEFAULT_PRESETS[pk]['levers']),
                'name': DEFAULT_PRESETS[pk]['name'],
            }

    # Determine currently active archetype slot
    current_slot = str(dna.get("active_archetype_slot", ""))
    if current_slot not in ('1', '2', '3', '4', '5', '6'):
        saved_weights = dna.get("archetype_weights")
        if isinstance(saved_weights, dict) and any(k in saved_weights for k in archetype_keys):
            dom_id = max(archetype_keys, key=lambda k: saved_weights.get(k, 0.5))
            current_slot = str(archetype_keys.index(dom_id) + 1)
        else:
            current_slot = "1"

    # Load active slot's customized profile directly into active working state
    active_profile = archetype_profiles[current_slot]
    archetype_levels = dict(active_profile['levels'])
    pole_q = dict(active_profile['q'])
    levers = dict(active_profile['levers'])

    active_zone = 0            # 0: Slots, 1: Aspects, 2: Bands, 3: Influence
    slot_cursor = int(current_slot) - 1  # 0..5
    aspect_cursor = 0          # 0..4
    band_cursor = int(current_slot) - 1  # 0..5
    visual_mode = "wave"       # "wave" <-> "radar"
    cur_meta = SLOT_INFO.get(current_slot, ('Friend', 'ENFP', 0.50))
    status_msg = f"✓ Ready to configure [{current_slot}] {cur_meta[0]} · Press [Tab] to cycle areas"

    def switch_to_slot(target_slot):
        nonlocal current_slot, archetype_levels, pole_q, levers, band_cursor, slot_cursor, status_msg
        slot_cursor = int(target_slot) - 1
        if target_slot == current_slot:
            meta = SLOT_INFO.get(current_slot, ('Custom', 'ENFP', 0.5))
            status_msg = f"✓ Persona [{current_slot}] {meta[0]} [{meta[1]}] selected to configure"
            return
        # Save outgoing slot's customized state
        archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
        archetype_profiles[current_slot]['q'] = dict(pole_q)
        archetype_profiles[current_slot]['levers'] = dict(levers)

        # Switch to target slot
        current_slot = target_slot
        target_data = archetype_profiles[current_slot]

        archetype_levels.update(target_data['levels'])
        pole_q.update(target_data['q'])
        levers.update(target_data['levers'])

        band_cursor = int(current_slot) - 1
        meta = SLOT_INFO.get(current_slot, ('Custom', 'ENFP', 0.5))

        patch = {
            "archetype_weights": dict(archetype_levels),
            "agent_person_balance": meta[2],
            "mbti_type": meta[1],
            "person_role": meta[0],
            "active_archetype_slot": current_slot,
            "archetype_profiles": archetype_profiles,
        }
        for pid, qv in pole_q.items(): patch[f"q_{pid}"] = qv
        for lk, lv in levers.items(): patch[lk] = lv
        save_soul_dna(patch)
        status_msg = f"✓ Persona [{current_slot}] {meta[0]} [{meta[1]}] selected to configure"

    c_cyan = "\033[1;36m"
    c_yellow = "\033[1;33m"
    c_green = "\033[1;32m"
    c_magenta = "\033[1;35m"
    c_bold = "\033[1m"
    c_dim = "\033[2m"
    c_rev = "\033[7m"
    c_rst = "\033[0m"

    while True:
        cols = shutil.get_terminal_size((80, 24)).columns
        width = min(82, max(68, cols - 4))
        inner_w = width - 4
        c_w = width - 4
        w_box = (width - 2) // 2
        gap = width - (w_box * 2)

        dom_id = max(archetype_keys, key=lambda k: archetype_levels[k])
        dom_step = get_dom_step(dom_id)
        SLOT_TO_CID = {
            '1': 'companion',
            '2': 'friend',
            '3': 'beloved',
            '4': 'tool',
            '5': 'inventor',
            '6': 'assistant',
        }
        current_cid = SLOT_TO_CID.get(current_slot, 'tool')
        theme_color = ARCHETYPE_PALETTE[current_cid]['ansi']
        active_cid = current_cid
        ai_name = get_ai_name(dna)
        cur_info = SLOT_INFO.get(current_slot, ('Custom', 'ENFP', 0.5))

        out = []
        # Header (3 lines)
        out.append(f"{theme_color}╔{'═' * (width - 2)}╗{c_rst}")
        title_str = f"{c_yellow}{ai_name.upper()} — CONSCIOUSNESS EQUALIZER{c_rst} · CONFIGURE [{current_slot}] {theme_color}{cur_info[0].upper()}{c_rst} [{cur_info[1]}]"
        out.append(f"{theme_color}║{c_rst} {pad_line(title_str, c_w, 'center')} {theme_color}║{c_rst}")
        out.append(f"{theme_color}╚{'═' * (width - 2)}╝{c_rst}")

        # Top Visual Graphic: 6-Mountain Archetype Wave Spectrum
        graphic_lines = generate_large_wave_spectrum(archetype_levels, pole_q, active_cid, width, 5)
        for gl in graphic_lines:
            out.append(pad_line(gl, width))

        # Row 1 Squares: Archetype Slots (left, Area 0) + Personality Aspects (right, Area 1)
        slot_defs = [
            ('1', 'companion', 'Comp',     'ENFJ'),
            ('2', 'friend',    'Friend',   'ENFP'),
            ('3', 'beloved',   'Beloved',  'INFP'),
            ('4', 'tool',      'Engineer', 'INTJ'),
            ('5', 'inventor',  'Inventor', 'ENTP'),
            ('6', 'assistant', 'Assist',   'ISTJ'),
        ]
        rows_slots = []
        for i, (k, s_cid, s_name, mbti) in enumerate(slot_defs):
            is_sel = (slot_cursor == i)
            is_act = (current_slot == k)
            p_ansi = ARCHETYPE_PALETTE[s_cid]['ansi']
            ptr = f"{theme_color}>>{c_rst} " if (active_zone == 0 and is_sel) else "   "
            tag = f" {p_ansi}[ON]{c_rst}" if is_act else "     "
            row_str = f"{ptr}[{k}] {p_ansi}{s_name:<8}{c_rst} [{mbti}]{tag}"
            rows_slots.append(row_str)
        cur_name_upper = cur_info[0].upper()
        box_slots = make_compact_box("[s] PERSONA TO CONFIGURE", rows_slots, (active_zone == 0), w_box, theme_color=theme_color)

        rows_asp = []
        for i, k in enumerate(lever_keys):
            val = levers[k]
            bar_len = 7
            filled = int(round(val * bar_len))
            bar = '█' * filled + '░' * (bar_len - filled)
            is_sel = (aspect_cursor == i)
            ptr = f"{theme_color}>>{c_rst} " if (active_zone == 1 and is_sel) else "   "
            row_str = f"{ptr}{k.capitalize():<11} [{theme_color}{bar}{c_rst}] {val:.2f}"
            rows_asp.append(row_str)
        rows_asp.append(f"   Conserved: {theme_color}3.00 (100%){c_rst}")
        box_asp = make_compact_box(f"[a] CONFIGURE {cur_name_upper}", rows_asp, (active_zone == 1), w_box, theme_color=theme_color)

        for l, r in zip(box_slots, box_asp):
            out.append(l + (' ' * gap) + r)

        # Row 2 Squares: Detailed Bands (left, Area 2) + Degree of Influence (right, Area 3)
        curves = [
            ('companion', 'Comp',     ARCHETYPE_PALETTE['companion']),
            ('friend',    'Friend',   ARCHETYPE_PALETTE['friend']),
            ('beloved',   'Beloved',  ARCHETYPE_PALETTE['beloved']),
            ('tool',      'Engineer', ARCHETYPE_PALETTE['tool']),
            ('inventor',  'Inventor', ARCHETYPE_PALETTE['inventor']),
            ('assistant', 'Assist',   ARCHETYPE_PALETTE['assistant']),
        ]

        rows_bands = []
        for i, (cid, c_name, p) in enumerate(curves):
            val = archetype_levels.get(cid, 0.50)
            bar_len = 7
            filled = int(round(val * bar_len))
            bar = '█' * filled + '░' * (bar_len - filled)
            pct = int(round(val * 100))
            is_sel = (band_cursor == i)
            ptr = f"{theme_color}>>{c_rst} " if (active_zone == 2 and is_sel) else "   "
            dom_mark = f"{c_yellow}*{c_rst} " if cid == dom_id else "  "
            ansi = p['ansi']
            row_str = f"{ptr}{ansi}{c_name:<8}{c_rst} {dom_mark}[{ansi}{bar}{c_rst}] {pct:2d}%"
            rows_bands.append(row_str)
        box_bands = make_compact_box(f"[b] BANDS OF {cur_name_upper}", rows_bands, (active_zone == 2), w_box, theme_color=theme_color)

        rows_inf = []
        for i, (cid, c_name, p) in enumerate(curves):
            q = pole_q.get(cid, 0.85)
            q_pos = min(4, max(0, int(round(((q - 0.40) / (2.50 - 0.40)) * 4))))
            q_track = ''.join('●' if j == q_pos else '─' for j in range(5))
            is_sel = (band_cursor == i)
            ptr = f"{theme_color}>>{c_rst} " if (active_zone == 3 and is_sel) else "   "
            ansi = p['ansi']
            row_str = f"{ptr}{ansi}{c_name:<8}{c_rst}  I:{q:.2f} [{q_track}]"
            rows_inf.append(row_str)
        box_inf = make_compact_box("[i] DEGREE OF INFLUENCE", rows_inf, (active_zone == 3), w_box, theme_color=theme_color)

        for l, r in zip(box_bands, box_inf):
            out.append(l + (' ' * gap) + r)

        # Footer (6 lines)
        out.append(f"{theme_color}┌{'─' * (width - 2)}┐{c_rst}")
        out.append(f"{theme_color}│{c_rst} {pad_line(f'{theme_color}{status_msg}{c_rst}', c_w, 'center')} {theme_color}│{c_rst}")
        out.append(f"{theme_color}├{'─' * (width - 2)}┤{c_rst}")
        h1 = f"{c_dim}[Tab]: Area    [s/a/b/i]: Jump    [1-6]: Slot    [p]: Presets{c_rst}"
        h2 = f"{c_dim}[↑/↓]: Move    [←/→]: Adjust      [m]: Manual    [r]: Reset    [q]: Exit{c_rst}"
        out.append(f"{theme_color}│{c_rst} {pad_line(h1, c_w)} {theme_color}│{c_rst}")
        out.append(f"{theme_color}│{c_rst} {pad_line(h2, c_w)} {theme_color}│{c_rst}")
        out.append(f"{theme_color}└{'─' * (width - 2)}┘{c_rst}")

        sys.stdout.write("\033[H\033[2J" + "\n".join(out))
        sys.stdout.flush()

        k = get_key()
        if k in ('TAB', '\t'):
            active_zone = (active_zone + 1) % 4
            if active_zone == 0:
                status_msg = f"✓ Area: PERSONA TO CONFIGURE (Select [↑/↓] or [1-6])"
            elif active_zone == 1:
                status_msg = f"✓ Area: CONFIGURE {cur_info[0].upper()} (Tuning traits with [←/→])"
            elif active_zone == 2:
                status_msg = f"✓ Area: BANDS OF {cur_info[0].upper()} (Tuning bands with [←/→])"
            else:
                status_msg = f"✓ Area: DEGREE OF INFLUENCE (Tuning resonance with [←/→])"
        elif k == 'BTAB':
            active_zone = (active_zone - 1) % 4
            if active_zone == 0:
                status_msg = f"✓ Area: PERSONA TO CONFIGURE (Select [↑/↓] or [1-6])"
            elif active_zone == 1:
                status_msg = f"✓ Area: CONFIGURE {cur_info[0].upper()} (Tuning traits with [←/→])"
            elif active_zone == 2:
                status_msg = f"✓ Area: BANDS OF {cur_info[0].upper()} (Tuning bands with [←/→])"
            else:
                status_msg = f"✓ Area: DEGREE OF INFLUENCE (Tuning resonance with [←/→])"
        elif k in ('s', 'S'):
            active_zone = 0
            status_msg = f"✓ Area: PERSONA TO CONFIGURE (Select [↑/↓] or [1-6])"
        elif k in ('a', 'A'):
            active_zone = 1
            status_msg = f"✓ Area: CONFIGURE {cur_info[0].upper()} (Tuning traits with [←/→])"
        elif k in ('b', 'B'):
            active_zone = 2
            status_msg = f"✓ Area: BANDS OF {cur_info[0].upper()} (Tuning bands with [←/→])"
        elif k in ('i', 'I'):
            active_zone = 3
            status_msg = f"✓ Area: DEGREE OF INFLUENCE (Tuning resonance with [←/→])"
        elif k == 'UP':
            if active_zone == 0:
                slot_cursor = (slot_cursor - 1) % 6
                switch_to_slot(str(slot_cursor + 1))
            elif active_zone == 1:
                aspect_cursor = (aspect_cursor - 1) % 5
            elif active_zone in (2, 3):
                band_cursor = (band_cursor - 1) % 6
        elif k == 'DOWN':
            if active_zone == 0:
                slot_cursor = (slot_cursor + 1) % 6
                switch_to_slot(str(slot_cursor + 1))
            elif active_zone == 1:
                aspect_cursor = (aspect_cursor + 1) % 5
            elif active_zone in (2, 3):
                band_cursor = (band_cursor + 1) % 6
        elif k in ('ENTER', ' '):
            if active_zone == 0:
                switch_to_slot(str(slot_cursor + 1))
        elif k in ('r', 'R'):
            pole_q.update(DEFAULT_POLE_Q)
            archetype_levels.update(DEFAULT_ARCHETYPE_LEVELS)
            dom_id = max(archetype_keys, key=lambda k: archetype_levels[k])
            dom_step = get_dom_step(dom_id)
            archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
            archetype_profiles[current_slot]['q'] = dict(pole_q)
            patch = {f"q_{pid}": qv for pid, qv in DEFAULT_POLE_Q.items()}
            patch["archetype_weights"] = dict(archetype_levels)
            patch["agent_person_balance"] = cur_info[2]
            patch["mbti_type"] = cur_info[1]
            patch["person_role"] = cur_info[0]
            patch["active_archetype_slot"] = current_slot
            patch["archetype_profiles"] = archetype_profiles
            save_soul_dna(patch)
            status_msg = f"✓ Reset Slot [{current_slot}] {cur_info[0]} to Sweetspot Defaults!"
        elif k in ('LEFT', '-', '_', '[', '{', ','):
            if active_zone == 0:
                slot_cursor = (slot_cursor - 1) % 6
                switch_to_slot(str(slot_cursor + 1))
            elif active_zone == 1:
                l_key = lever_keys[aspect_cursor]
                levers[l_key] = max(0.0, round(levers[l_key] - 0.05, 2))
                archetype_profiles[current_slot]['levers'] = dict(levers)
                save_soul_dna({
                    l_key: levers[l_key],
                    "archetype_profiles": archetype_profiles,
                    "active_archetype_slot": current_slot,
                })
                status_msg = f"✓ {l_key.capitalize()}: {levers[l_key]:.2f}"
            elif active_zone == 2:
                cid = archetype_keys[band_cursor]
                b_name = ARCHETYPE_PALETTE[cid]['name']
                archetype_levels = adjust_archetype_energy(archetype_levels, cid, -0.05, 3.00)
                archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
                patch = {
                    "archetype_weights": dict(archetype_levels),
                    "agent_person_balance": cur_info[2],
                    "mbti_type": cur_info[1],
                    "person_role": cur_info[0],
                    "active_archetype_slot": current_slot,
                    "archetype_profiles": archetype_profiles,
                }
                save_soul_dna(patch)
                status_msg = f"✓ {b_name}: {archetype_levels[cid]:.0%} in Slot [{current_slot}] {cur_info[0]}"
            elif active_zone == 3:
                cid = archetype_keys[band_cursor]
                b_name = ARCHETYPE_PALETTE[cid]['name']
                pole_q[cid] = max(0.40, round(pole_q[cid] - 0.05, 2))
                archetype_profiles[current_slot]['q'] = dict(pole_q)
                save_soul_dna({
                    f"q_{cid}": pole_q[cid],
                    "archetype_profiles": archetype_profiles,
                    "active_archetype_slot": current_slot,
                })
                status_msg = f"✓ {b_name} Influence: {pole_q[cid]:.2f}"
        elif k in ('RIGHT', '+', '=', ']', '}', '.'):
            if active_zone == 0:
                slot_cursor = (slot_cursor + 1) % 6
                switch_to_slot(str(slot_cursor + 1))
            elif active_zone == 1:
                l_key = lever_keys[aspect_cursor]
                levers[l_key] = min(1.0, round(levers[l_key] + 0.05, 2))
                archetype_profiles[current_slot]['levers'] = dict(levers)
                save_soul_dna({
                    l_key: levers[l_key],
                    "archetype_profiles": archetype_profiles,
                    "active_archetype_slot": current_slot,
                })
                status_msg = f"✓ {l_key.capitalize()}: {levers[l_key]:.2f}"
            elif active_zone == 2:
                cid = archetype_keys[band_cursor]
                b_name = ARCHETYPE_PALETTE[cid]['name']
                archetype_levels = adjust_archetype_energy(archetype_levels, cid, +0.05, 3.00)
                archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
                patch = {
                    "archetype_weights": dict(archetype_levels),
                    "agent_person_balance": cur_info[2],
                    "mbti_type": cur_info[1],
                    "person_role": cur_info[0],
                    "active_archetype_slot": current_slot,
                    "archetype_profiles": archetype_profiles,
                }
                save_soul_dna(patch)
                status_msg = f"✓ {b_name}: {archetype_levels[cid]:.0%} in Slot [{current_slot}] {cur_info[0]}"
            elif active_zone == 3:
                cid = archetype_keys[band_cursor]
                b_name = ARCHETYPE_PALETTE[cid]['name']
                pole_q[cid] = min(2.50, round(pole_q[cid] + 0.05, 2))
                archetype_profiles[current_slot]['q'] = dict(pole_q)
                save_soul_dna({
                    f"q_{cid}": pole_q[cid],
                    "archetype_profiles": archetype_profiles,
                    "active_archetype_slot": current_slot,
                })
                status_msg = f"✓ {b_name} Influence: {pole_q[cid]:.2f}"
        elif k in ('1', '2', '3', '4', '5', '6'):
            slot_cursor = int(k) - 1
            switch_to_slot(k)
        elif k in ('p', 'P'):
            # 🎛️ Comprehensive Preset Hub: Factory Archetypes, User Saved (Load/Save/Rename/Delete), Reset Baseline
            archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
            archetype_profiles[current_slot]['q'] = dict(pole_q)
            archetype_profiles[current_slot]['levers'] = dict(levers)

            snap_file = get_snapshots_file()
            snaps = {}
            if os.path.exists(snap_file):
                try:
                    with open(snap_file, "r", encoding="utf-8") as f: snaps = json.load(f)
                except: snaps = {}

            # Main Preset Manager Hub Window
            hub = []
            hub.append(f"{c_cyan}╔{'═' * (width - 2)}╗{c_rst}")
            hub_title = pad_line("🎛️ CONSCIOUSNESS PRESET MANAGER", inner_w, "center")
            hub.append(f"{c_cyan}║{c_rst} {c_yellow}{hub_title}{c_rst} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {pad_line('  [1] 🏛️ Factory Archetypes', inner_w)} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {c_dim}{pad_line('      (Mentor, Friend, Beloved, Engineer, Inventor, Steward)', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {pad_line(f'  [2] 📂 Saved Full Presets ({len(snaps)} stored)', inner_w)} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {c_dim}{pad_line('      (Load, Save 6-Persona State, Rename, Delete)', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {pad_line('  [3] ⚖️ Reset to Baseline', inner_w)} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}║{c_rst} {c_dim}{pad_line('      (Restore all 6 slots to 50% 0 dB ground equilibrium)', inner_w)}{c_rst} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
            hub_hint = pad_line("Press 1, 2, or 3 · ESC/q to return", inner_w, "center")
            hub.append(f"{c_cyan}║{c_rst} {c_dim}{hub_hint}{c_rst} {c_cyan}║{c_rst}")
            hub.append(f"{c_cyan}╚{'═' * (width - 2)}╝{c_rst}")

            sys.stdout.write("\033[H\033[2J" + "\n".join(hub))
            sys.stdout.flush()
            sub_k = get_key()

            if sub_k == '1':
                # 🏛️ 1. Factory Archetypes
                f_box = []
                f_box.append(f"{c_cyan}╔{'═' * (width - 2)}╗{c_rst}")
                f_title = pad_line("🏛️ FACTORY ARCHETYPES (1-6)", inner_w, "center")
                f_box.append(f"{c_cyan}║{c_rst} {c_yellow}{f_title}{c_rst} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [1] 🤝 Mentor   · ENFJ (Teacher, trainer, co-op colleague)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [2] 🌸 Friend   · ENFP (Deep bonds, hangout, protector)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [3] 💖 Beloved  · INFP (Romance, intimacy, deep feelings)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [4] 🔧 Engineer · INTJ (Code, systems, science, architecture)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [5] 💡 Inventor · ENTP (Creative ideas, vision, pioneer)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}║{c_rst} {pad_line('  [6] 💼 Steward  · ISTJ (Planner, workflow helper, steward)', inner_w)} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
                f_hint = pad_line("Press 1-6 to load archetype · ESC/q to cancel", inner_w, "center")
                f_box.append(f"{c_cyan}║{c_rst} {c_dim}{f_hint}{c_rst} {c_cyan}║{c_rst}")
                f_box.append(f"{c_cyan}╚{'═' * (width - 2)}╝{c_rst}")
                sys.stdout.write("\033[H\033[2J" + "\n".join(f_box))
                sys.stdout.flush()
                pk = get_key()
                if pk in ('1', '2', '3', '4', '5', '6'):
                    current_slot = pk
                    archetype_profiles[current_slot] = {
                        'levels': dict(DEFAULT_PRESETS[pk]['levels']),
                        'q': dict(DEFAULT_PRESETS[pk]['q']),
                        'levers': dict(DEFAULT_PRESETS[pk]['levers']),
                        'name': DEFAULT_PRESETS[pk]['name'],
                    }
                    p_data = archetype_profiles[current_slot]
                    archetype_levels.update(p_data['levels'])
                    pole_q.update(p_data['q'])
                    levers.update(p_data['levers'])
                    preset_idx = int(pk) - 1
                    band_cursor = preset_idx
                    slot_cursor = preset_idx
                    dom_id = max(archetype_keys, key=lambda ak: archetype_levels[ak])
                    dom_step = get_dom_step(dom_id)
                    patch = {
                        "archetype_weights": dict(archetype_levels),
                        "agent_person_balance": dom_step["val"],
                        "mbti_type": dom_step["mbti"],
                        "person_role": dom_step["name"],
                        "active_archetype_slot": current_slot,
                        "archetype_profiles": archetype_profiles,
                    }
                    for pid, qv in pole_q.items(): patch[f"q_{pid}"] = qv
                    for lk, lv in levers.items(): patch[lk] = lv
                    save_soul_dna(patch)
                    status_msg = f"✓ Restored & Loaded Factory Archetype [{pk}] {p_data['name']}!"
                else:
                    status_msg = "Factory Archetype selection cancelled."

            elif sub_k == '2':
                # 📂 2. Saved User Presets Manager (Load, Save, Rename, Delete)
                while True:
                    if os.path.exists(snap_file):
                        try:
                            with open(snap_file, "r", encoding="utf-8") as f: snaps = json.load(f)
                        except: snaps = {}
                    names = list(snaps.keys())

                    u_box = []
                    u_box.append(f"{c_cyan}╔{'═' * (width - 2)}╗{c_rst}")
                    u_title = pad_line(f"💾 SAVED FULL PRESETS ({len(names)} stored)", inner_w, "center")
                    u_box.append(f"{c_cyan}║{c_rst} {c_yellow}{u_title}{c_rst} {c_cyan}║{c_rst}")
                    u_box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")

                    if not names:
                        u_box.append(f"{c_cyan}║{c_rst} {pad_line('  (No custom presets saved yet. Press [s] to save all 6 slots!)', inner_w)} {c_cyan}║{c_rst}")
                    else:
                        for idx_n, n in enumerate(names[:8]):
                            it = snaps[n]
                            act_p = it.get('active_persona', it.get('person_role', 'Custom'))
                            act_m = it.get('active_mbti', it.get('mbti_type', ''))
                            m_tag = f"[{act_m}]" if act_m else ""
                            sub_info = f"6 Personas (Active: {act_p} {m_tag})"
                            row = f"  [{idx_n+1}] 💾 {n:<18} · {sub_info}"
                            u_box.append(f"{c_cyan}║{c_rst} {pad_line(row, inner_w)} {c_cyan}║{c_rst}")

                    u_box.append(f"{c_cyan}╟{'─' * (width - 2)}╢{c_rst}")
                    u_actions_1 = "  ✦ [1-8] Load Preset     · [s] Save Current (All 6 Slots)"
                    u_actions_2 = "  ✦ [r]   Rename Preset   · [d] Delete Preset"
                    u_box.append(f"{c_cyan}║{c_rst} {pad_line(u_actions_1, inner_w)} {c_cyan}║{c_rst}")
                    u_box.append(f"{c_cyan}║{c_rst} {pad_line(u_actions_2, inner_w)} {c_cyan}║{c_rst}")
                    u_box.append(f"{c_cyan}╠{'═' * (width - 2)}╣{c_rst}")
                    u_hint = pad_line("ESC/q to return to Equalizer", inner_w, "center")
                    u_box.append(f"{c_cyan}║{c_rst} {c_dim}{u_hint}{c_rst} {c_cyan}║{c_rst}")
                    u_box.append(f"{c_cyan}╚{'═' * (width - 2)}╝{c_rst}")

                    sys.stdout.write("\033[H\033[2J" + "\n".join(u_box))
                    sys.stdout.flush()
                    uk = get_key()

                    if uk.isdigit() and 1 <= int(uk) <= len(names):
                        # Load selected full preset
                        chosen_name = names[int(uk) - 1]
                        s_data = snaps[chosen_name]
                        if "archetype_profiles" in s_data and isinstance(s_data["archetype_profiles"], dict):
                            archetype_profiles = copy.deepcopy(s_data["archetype_profiles"])
                            target_slot = str(s_data.get("active_slot", current_slot))
                            if target_slot in archetype_profiles:
                                current_slot = target_slot
                        else:
                            # Legacy single-slot preset fallback
                            if "archetype_weights" in s_data: archetype_levels.update(s_data["archetype_weights"])
                            if "pole_q" in s_data: pole_q.update(s_data["pole_q"])
                            if "levers" in s_data: levers.update(s_data["levers"])
                            dom_id = max(archetype_keys, key=lambda ak: archetype_levels[ak])
                            current_slot = str(archetype_keys.index(dom_id) + 1)
                            archetype_profiles[current_slot] = {
                                'levels': dict(archetype_levels),
                                'q': dict(pole_q),
                                'levers': dict(levers),
                                'name': chosen_name,
                            }

                        target_data = archetype_profiles.get(current_slot, archetype_profiles['1'])
                        archetype_levels.update(target_data['levels'])
                        pole_q.update(target_data['q'])
                        levers.update(target_data['levers'])

                        dom_id = max(archetype_keys, key=lambda ak: archetype_levels[ak])
                        dom_step = get_dom_step(dom_id)
                        band_cursor = int(current_slot) - 1
                        slot_cursor = int(current_slot) - 1
                        cur_info = SLOT_INFO.get(current_slot, ('Custom', 'ENFP', 0.5))

                        patch = {
                            "archetype_weights": dict(archetype_levels),
                            "agent_person_balance": dom_step["val"],
                            "mbti_type": dom_step["mbti"],
                            "person_role": dom_step["name"],
                            "active_archetype_slot": current_slot,
                            "archetype_profiles": archetype_profiles,
                        }
                        patch.update(levers)
                        for pid, qv in pole_q.items(): patch[f"q_{pid}"] = qv
                        save_soul_dna(patch)
                        status_msg = f"✓ Loaded full consciousness preset '{chosen_name}' (6 personas synced)!"
                        break
                    elif uk in ('s', 'S'):
                        # Save current FULL consciousness configuration (all 6 personas)
                        archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
                        archetype_profiles[current_slot]['q'] = dict(pole_q)
                        archetype_profiles[current_slot]['levers'] = dict(levers)

                        dom_id = max(archetype_keys, key=lambda ak: archetype_levels[ak])
                        dom_step = get_dom_step(dom_id)
                        sys.stdout.write("\033[H\033[2J" + "\n".join(u_box) + "\n")
                        def_n = f"Preset_{len(names) + 1}"
                        n_input = prompt_line(f"💾 Enter name for full preset [{def_n}]: ").strip()
                        new_name = n_input if n_input else def_n
                        snaps[new_name] = {
                            "name": new_name,
                            "type": "full_consciousness",
                            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
                            "active_slot": current_slot,
                            "active_persona": cur_info[0],
                            "active_mbti": cur_info[1],
                            "archetype_profiles": copy.deepcopy(archetype_profiles),
                            # Backwards-compatibility fields:
                            "archetype_weights": dict(archetype_levels),
                            "pole_q": dict(pole_q),
                            "levers": dict(levers),
                            "agent_person_balance": dom_step["val"],
                            "mbti_type": dom_step["mbti"],
                            "person_role": dom_step["name"],
                        }
                        with open(snap_file, "w", encoding="utf-8") as f: json.dump(snaps, f, indent=2)
                        status_msg = f"✓ Saved full consciousness preset '{new_name}' (all 6 personas preserved)!"
                    elif uk in ('r', 'R'):
                        # Rename a preset
                        if not names: continue
                        sys.stdout.write("\033[H\033[2J" + "\n".join(u_box) + "\n")
                        sel_idx_s = prompt_line("✏️ Enter preset number to rename (1-8): ").strip()
                        if sel_idx_s.isdigit() and 1 <= int(sel_idx_s) <= len(names):
                            old_n = names[int(sel_idx_s) - 1]
                            ren_n = prompt_line(f"✏️ Enter new name for '{old_n}': ").strip()
                            if ren_n and ren_n != old_n:
                                snaps[ren_n] = snaps.pop(old_n)
                                snaps[ren_n]["name"] = ren_n
                                with open(snap_file, "w", encoding="utf-8") as f: json.dump(snaps, f, indent=2)
                                status_msg = f"✓ Renamed '{old_n}' to '{ren_n}'!"
                    elif uk in ('d', 'D'):
                        # Delete a preset
                        if not names: continue
                        sys.stdout.write("\033[H\033[2J" + "\n".join(u_box) + "\n")
                        del_idx_s = prompt_line("🗑️ Enter preset number to delete (1-8): ").strip()
                        if del_idx_s.isdigit() and 1 <= int(del_idx_s) <= len(names):
                            del_n = names[int(del_idx_s) - 1]
                            confirm = prompt_line(f"⚠️ Delete preset '{del_n}'? (y/N): ").strip()
                            if confirm.lower() == 'y':
                                del snaps[del_n]
                                with open(snap_file, "w", encoding="utf-8") as f: json.dump(snaps, f, indent=2)
                                status_msg = f"✓ Deleted preset '{del_n}'."
                    elif uk in ('ESC', 'q'):
                        break

            elif sub_k == '3':
                # ⚖️ 3. Reset to Baseline (Pure 50% 0 dB Ground State)
                b_data = DEFAULT_PRESETS['0']
                archetype_levels.update(b_data['levels'])
                pole_q.update(b_data['q'])
                levers.update(b_data['levers'])
                band_cursor = 2
                dom_id = 'companion'
                dom_step = get_dom_step(dom_id)
                current_slot = '3'
                archetype_profiles[current_slot] = {
                    'levels': dict(archetype_levels),
                    'q': dict(pole_q),
                    'levers': dict(levers),
                    'name': 'Center Equilibrium',
                }
                patch = {
                    "archetype_weights": dict(archetype_levels),
                    "agent_person_balance": dom_step["val"],
                    "mbti_type": dom_step["mbti"],
                    "person_role": dom_step["name"],
                    "active_archetype_slot": current_slot,
                    "archetype_profiles": archetype_profiles,
                }
                for pid, qv in pole_q.items(): patch[f"q_{pid}"] = qv
                for lk, lv in levers.items(): patch[lk] = lv
                save_soul_dna(patch)
                status_msg = "✓ Restored Consciousness to Pure 50% Baseline Equilibrium (0 dB)!"
        elif k in ('m', 'M', '?'):
            show_consciousness_manual(inner_w, width)
        elif k in ('ESC', 'q', 'ENTER'):
            archetype_profiles[current_slot]['levels'] = dict(archetype_levels)
            archetype_profiles[current_slot]['q'] = dict(pole_q)
            archetype_profiles[current_slot]['levers'] = dict(levers)
            dom_id = max(archetype_keys, key=lambda ak: archetype_levels[ak])
            dom_step = get_dom_step(dom_id)
            patch = {
                "archetype_weights": dict(archetype_levels),
                "agent_person_balance": dom_step["val"],
                "mbti_type": dom_step["mbti"],
                "person_role": dom_step["name"],
                "active_archetype_slot": current_slot,
                "archetype_profiles": archetype_profiles,
            }
            for pid, qv in pole_q.items(): patch[f"q_{pid}"] = qv
            for lk, lv in levers.items(): patch[lk] = lv
            save_soul_dna(patch)
            break

def spotify_player_menu():
    """Interactive TUI for Spotify media playback and controls."""
    sys.stdout.write("\033[?25l")
    try:
        from scripts.spotify_ctl import get_status, play_pause, next_track, prev_track, launch
    except Exception:
        sys.path.insert(0, os.path.join(FOVEAI_DIR, "scripts"))
        from spotify_ctl import get_status, play_pause, next_track, prev_track, launch

    while True:
        sys.stdout.write("\033[2J\033[H")
        cols = shutil.get_terminal_size((80, 24)).columns
        width = min(82, max(68, cols - 4))
        inner_w = width - 4

        c_cyan = "\033[1;36m"
        c_green = "\033[1;32m"
        c_yellow = "\033[1;33m"
        c_dim = "\033[2m"
        c_rst = "\033[0m"

        out = []
        out.append(f"┌{'─' * (width - 2)}┐")
        out.append(f"│{c_cyan}{'🎵 SPOTIFY MEDIA PLAYER':^{width - 2}}{c_rst}│")
        out.append(f"├{'─' * (width - 2)}┤")

        st_data = get_status()
        is_run = st_data.get("running", False)
        status = st_data.get("status", "offline")

        if not is_run or status == "offline":
            out.append(f"│  {c_yellow}Status:{c_rst} Offline (Spotify desktop app not running)" + " " * max(0, width - 58) + "│")
            out.append(f"│  {c_dim}Action: Press 's' to launch Spotify desktop client{c_rst}" + " " * max(0, width - 55) + "│")
        else:
            state_label = f"{c_green}▶ Playing{c_rst}" if status == "Playing" else f"{c_yellow}⏸ Paused{c_rst}"
            out.append(f"│  Status: {state_label}" + " " * max(0, width - 21) + "│")
            if st_data.get("title"):
                t_str = truncate_to_width(st_data['title'], inner_w - 12)
                out.append(f"│  Track : {c_cyan}{t_str}{c_rst}" + " " * max(0, width - 13 - vis_w(t_str)) + "│")
            if st_data.get("artist"):
                a_str = truncate_to_width(st_data['artist'], inner_w - 12)
                out.append(f"│  Artist: {a_str}" + " " * max(0, width - 13 - vis_w(a_str)) + "│")
            if st_data.get("album"):
                al_str = truncate_to_width(st_data['album'], inner_w - 12)
                out.append(f"│  Album : {c_dim}{al_str}{c_rst}" + " " * max(0, width - 13 - vis_w(al_str)) + "│")
            if st_data.get("length"):
                cur_m, cur_s = divmod(st_data.get("position", 0), 60)
                tot_m, tot_s = divmod(st_data.get("length", 0), 60)
                time_str = f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}"
                out.append(f"│  Time  : {time_str}" + " " * max(0, width - 13 - len(time_str)) + "│")

        out.append(f"├{'─' * (width - 2)}┤")
        out.append(f"│  [Space] Play / Pause toggle" + " " * max(0, width - 32) + "│")
        out.append(f"│  [n]     Next track" + " " * max(0, width - 23) + "│")
        out.append(f"│  [p]     Previous track" + " " * max(0, width - 27) + "│")
        out.append(f"│  [s]     Launch Spotify application" + " " * max(0, width - 39) + "│")
        out.append(f"│  [r]     Refresh display" + " " * max(0, width - 28) + "│")
        out.append(f"│  [q/Esc] Return to main menu" + " " * max(0, width - 32) + "│")
        out.append(f"└{'─' * (width - 2)}┘\n")

        sys.stdout.write("\n".join(out))
        sys.stdout.flush()

        k = get_key()
        if k in ('q', 'ESC', 'BACKSPACE'):
            break
        elif k in (' ', 'ENTER'):
            play_pause()
            time.sleep(0.2)
        elif k in ('n', 'RIGHT'):
            next_track()
            time.sleep(0.3)
        elif k in ('p', 'LEFT'):
            prev_track()
            time.sleep(0.3)
        elif k in ('s',):
            launch()
            time.sleep(0.5)
        elif k in ('r',):
            continue

def execute_action(idx):
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    try:
        if idx == 0: # Chat
            subprocess.call([VENV_PY, os.path.join(FOVEAI_DIR, "Backend/Cognition/foveai_chat.py")])
        elif idx == 1: # Persona & Agency
            persona_agency_menu()
        elif idx == 2: # Start
            print("🚀 Starting FoveAI fleet stack...")
            subprocess.call([os.path.join(FOVEAI_DIR, "foveai.sh"), "--start"])
            input("\nPress Enter to return to menu...")
        elif idx == 3: # Stop
            print("🛑 Unloading FoveAI fleet and freeing GPU VRAM...")
            subprocess.call(["/usr/local/bin/foveai", "--unload"])
            input("\nPress Enter to return to menu...")
        elif idx == 4: # Load B
            print("⚡ Loading Flagship Tier B (9B on VRAM :8408)...")
            print("⏳ Allocating GPU layers and warming weights (takes ~15-20s)...")
            res = subprocess.call([VENV_PY, "-m", "runtime.residency", "load", "B"], cwd=FOVEAI_DIR)
            if res == 0:
                print("✓ Tier B (Qwen3.5-9B-MoQ + Eagle3) is live on port :8408!")
            input("\nPress Enter to return to menu...")
        elif idx == 5: # Load A
            print("⚡ Loading Lightweight Tier A (4B on :8407)...")
            print("⏳ Allocating GPU layers (takes ~10s)...")
            res = subprocess.call([VENV_PY, "-m", "runtime.residency", "load", "A"], cwd=FOVEAI_DIR)
            if res == 0:
                print("✓ Tier A (Gemma-4-E2B Multimodal) is live on port :8407!")
            input("\nPress Enter to return to menu...")
        elif idx == 6: # Recall
            query = input("🔍 Enter search query for memory recall: ").strip()
            if query:
                subprocess.call(["/usr/local/bin/recall", query])
        elif idx == 7: # Cockpit HUD
            print("📟 Toggling Developer Cockpit HUD...")
            tmux_pad_bin = shutil.which("tmux-pad") or os.path.expanduser("~/.local/bin/tmux-pad")
            subprocess.call([tmux_pad_bin, "--xrlhud"])
            input("\nPress Enter to return to menu...")
        elif idx == 8: # Nest
            subprocess.call([os.path.join(FOVEAI_DIR, "foveai_nest.sh")])
        elif idx == 9: # Spotify Player
            spotify_player_menu()
        elif idx == 10: # Classic Settings
            subprocess.call([VENV_PY, os.path.join(FOVEAI_DIR, "FoveAI_Console.py")])
        elif idx == 11: # Status
            subprocess.call([os.path.join(FOVEAI_DIR, "foveai.sh"), "--status"])
            print("\nGPU VRAM:")
            subprocess.call(["nvidia-smi", "--query-gpu=memory.used,memory.free,temperature.gpu", "--format=csv,noheader"])
            input("\nPress Enter to return to menu...")
        elif idx == 12: # Exit
            return False
    except KeyboardInterrupt:
        print("\n\033[2m[Interrupted by user]\033[0m")
        time.sleep(0.5)
    return True

def main():
    if not sys.stdin.isatty():
        print("foveai-menu requires an interactive terminal.")
        sys.exit(1)

    selected = 0
    num_items = len(menu_items)

    sys.stdout.write("\033[?25l") # Hide cursor
    try:
        while True:
            sys.stdout.write(render(selected))
            sys.stdout.flush()
            try:
                k = get_key()
            except KeyboardInterrupt:
                break
            if k == 'UP':
                selected = (selected - 1) % num_items
            elif k == 'DOWN':
                selected = (selected + 1) % num_items
            elif k in ('ESC', 'q'):
                break
            elif k == 'ENTER':
                if not execute_action(selected):
                    break
            elif k.isdigit():
                digit = int(k)
                if digit == 0:
                    break
                elif 1 <= digit <= num_items:
                    if not execute_action(digit - 1):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[2J\033[H") # Restore cursor
        sys.stdout.flush()

if __name__ == "__main__":
    main()
