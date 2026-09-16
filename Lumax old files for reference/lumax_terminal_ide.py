# ───────────────────────────────────────────────────────────────
#  LUMAX TERMINAL IDE — CHUNK 1
#  Imports + Theme + Core Layout + Virtual Canvas Scaffolding
# ───────────────────────────────────────────────────────────────

from pathlib import Path
from typing import Optional, List, Tuple

import json
import requests

from pygments import highlight
from pygments.lexers import guess_lexer_for_filename, PythonLexer
from pygments.formatters import TerminalFormatter

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Static,
    Button,
    RichLog,
    Input,
    Tree,
    Label,
)
from textual.screen import ModalScreen
from textual.reactive import reactive
from textual import events
from rich.text import Text


# ───────────────────────────────────────────────────────────────
#  GLOBAL THEME COLORS (Lumax Neon)
# ───────────────────────────────────────────────────────────────

LUMAX_CYAN = "#00eaff"      # User bubble + glow
LUMAX_PURPLE = "#a020f0"    # AI bubble + glow
LUMAX_BG = "#0a0a0f"        # Global background
LUMAX_PANEL_BG = "#0b0b12"  # Dark glass panel background
LUMAX_GLOW = "#00ffff55"    # Neon pulse


# ───────────────────────────────────────────────────────────────
#  RESPONSIVE LAYOUT MODES
# ───────────────────────────────────────────────────────────────

def compute_layout_mode(width: int, height: int) -> str:
    """
    Returns one of:
    - "compact"
    - "wide"
    - "ultra"
    """
    if width > 200 and height > 60:
        return "ultra"
    if width > 140:
        return "wide"
    return "compact"


# ───────────────────────────────────────────────────────────────
#  VIRTUAL CANVAS SUPPORT
# ───────────────────────────────────────────────────────────────

class VirtualCanvas:
    """
    A virtual rendering surface larger than the terminal.
    Editor and chat can be taller than the terminal.
    """
    def __init__(self):
        self.virtual_height = 200  # can be expanded dynamically
        self.virtual_width = 200

    def resize(self, width: int, height: int):
        # Expand virtual canvas proportionally
        self.virtual_width = max(self.virtual_width, width)
        self.virtual_height = max(self.virtual_height, height)


# ───────────────────────────────────────────────────────────────
#  CORE LAYOUT CONTAINERS
# ───────────────────────────────────────────────────────────────

class LumaxTerminalIDE(App):

    CSS = f"""
    Screen {{
        background: {LUMAX_BG};
    }}

    #main-layout {{
        height: 100%;
        width: 100%;
        padding-bottom: 2;
    }}

    /* LEFT SIDE: Editor + Chat stacked */
    #left-pane {{
        width: 68%;
        background: {LUMAX_PANEL_BG};
    }}

    #editor-pane {{
        height: 50%;
        border: round {LUMAX_CYAN};
        background: {LUMAX_PANEL_BG};
        padding: 1;
    }}

    #chat-pane {{
        height: 50%;
        border: round {LUMAX_PURPLE};
        background: {LUMAX_PANEL_BG};
        padding: 1;
    }}

    /* RIGHT SIDE: Logs + File Tree + Diff + Menu */
    #right-pane {{
        width: 32%;
    }}

    #logs-pane {{
        height: 30%;
        border: round #333;
        background: {LUMAX_PANEL_BG};
        padding: 1;
    }}

    #files-pane {{
        height: 30%;
        border: round #444;
        background: {LUMAX_PANEL_BG};
        padding: 1;
    }}

    #diff-pane {{
        height: 20%;
        border: round #555;
        background: {LUMAX_PANEL_BG};
        padding: 1;
    }}

    #menu-bar {{
        height: auto;
        background: #111;
        border: round {LUMAX_CYAN};
        padding: 1;
        layout: grid;
        grid-size: 2;
    }}

    #menu-bar Button {{
        width: 100%;
        background: #0d0d15;
        color: {LUMAX_CYAN};
        border: round {LUMAX_CYAN};
    }}

    /* DIVIDERS */
    #divider-vertical {{
        width: 1;
        background: #222;
    }}

    #divider-horizontal {{
        height: 1;
        background: #222;
    }}
    """

    # Reactive states for dynamic expansion
    editor_expanded = reactive(False)
    chat_expanded = reactive(False)

    # Virtual canvas
    canvas = VirtualCanvas()

    def on_mount(self) -> None:
        self.backend_config = BackendConfig()
        self._install_controllers()
        self._mouse_handlers()
        self._click_handlers()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings":
            self.push_screen(SettingsModal(self.backend_config))
        elif event.button.id == "model":
            self.push_screen(ModelSelectorModal(self.backend_config))
        elif event.button.id == "save":
            try:
                editor = self.query_one("#editor-pane")
                if hasattr(editor, "save"):
                    editor.save()
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        """
        Core layout:
        Left side: Editor + Chat stacked
        Right side: Logs + Files + Diff + Menu
        """
        yield Container(
            Horizontal(
                # LEFT SIDE
                Vertical(
                    CodeEditor(id="editor-pane"),
                    Static(id="divider-horizontal"),
                    ChatPane(id="chat-pane"),
                    id="left-pane",
                ),

                Static(id="divider-vertical"),

                # RIGHT SIDE
                Vertical(
                    LogsPane(id="logs-pane"),
                    FileTree("Workspace", id="files-pane"),
                    DiffViewer(id="diff-pane"),
                    Container(
                        Button("Attach", id="attach"),
                        Button("Save", id="save"),
                        Button("Share", id="share"),
                        Button("Model", id="model"),
                        Button("Settings", id="settings"),
                        id="menu-bar",
                    ),
                    id="right-pane",
                ),

                id="main-layout",
            )
        )

    # ───────────────────────────────────────────────────────────────
    #  RESPONSIVE RESIZE HANDLING
    # ───────────────────────────────────────────────────────────────

    def on_resize(self, event: events.Resize) -> None:
        width, height = event.size
        mode = compute_layout_mode(width, height)
        self.canvas.resize(width, height)

        try:
            logs = self.query_one("#logs-pane")
            if hasattr(logs, "clear"):
                logs.clear()
                logs.write(f"Resize detected: {width}x{height} mode={mode}")
            else:
                logs.update(f"Resize detected: {width}x{height} mode={mode}")
        except Exception:
            pass


# ───────────────────────────────────────────────────────────────
#  CHUNK 2 — CodeEditor + ChatPane Widgets
# ───────────────────────────────────────────────────────────────

class CodeEditor(RichLog):
    """Syntax-highlighted code editor."""
    can_focus = True
    file_path: Optional[Path] = None
    buffer: str = ""
    lexer = PythonLexer()

    def on_mount(self) -> None:
        self.border_title = "Code Editor"
        self.write("")  # ensure widget is initialized

    def set_file(self, path: Path):
        self.file_path = path
        if path.exists():
            self.buffer = path.read_text(encoding="utf-8", errors="ignore")
        else:
            self.buffer = ""
        self._detect_lexer()
        self._render_buffer()

    def _detect_lexer(self):
        if self.file_path:
            try:
                self.lexer = guess_lexer_for_filename(
                    self.file_path.name, self.buffer or ""
                )
            except Exception:
                self.lexer = PythonLexer()

    def _render_buffer(self):
        self.clear()
        highlighted = highlight(self.buffer, self.lexer, TerminalFormatter())
        self.write(highlighted)

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            self.buffer = self.buffer[:-1]
        elif event.key == "enter":
            self.buffer += "\n"
        elif len(event.key) == 1:
            self.buffer += event.key
        self._render_buffer()

    def save(self):
        if self.file_path:
            self.file_path.write_text(self.buffer, encoding="utf-8")


class ChatPane(RichLog):
    """Hybrid chat pane: user/AI messages + highlighted code blocks."""
    def on_mount(self) -> None:
        self.border_title = "Chat"
        self.write("Chat ready.\n")

    def add_user_message(self, text: str):
        msg = Text(f"\n[You]\n", style=LUMAX_CYAN)
        self.write(msg)
        body = Text(text + "\n", style="white")
        self.write(body)

    def add_ai_message(self, text: str):
        msg = Text(f"\n[AI]\n", style=LUMAX_PURPLE)
        self.write(msg)
        body = Text(text + "\n", style="white")
        self.write(body)

    def add_ai_code_block(self, code: str):
        highlighted = highlight(code, PythonLexer(), TerminalFormatter())
        hdr = Text("\n[AI Code]\n", style=LUMAX_PURPLE)
        self.write(hdr)
        self.write(highlighted)

    def add_system_message(self, text: str):
        sys_msg = Text(f"\n[System] {text}\n", style="grey")
        self.write(sys_msg)


# ───────────────────────────────────────────────────────────────
#  CHUNK 3 — Dynamic Expansion, Animations, Draggable Dividers
# ───────────────────────────────────────────────────────────────

# Editor/chat expansion ratios
EDITOR_EXPANDED_RATIO = 0.85
CHAT_EXPANDED_RATIO = 0.85
COLLAPSED_RATIO = 0.15
DEFAULT_RATIO = 0.50


class PaneController:
    """
    Controls dynamic expansion/collapse of editor and chat panes.
    Handles animations and ratio transitions.
    """
    def __init__(self, app: "LumaxTerminalIDE"):
        self.app = app

    def expand_editor(self):
        self.app.editor_expanded = True
        self.app.chat_expanded = False
        self._animate_panes(EDITOR_EXPANDED_RATIO, COLLAPSED_RATIO)

    def expand_chat(self):
        self.app.editor_expanded = False
        self.app.chat_expanded = True
        self._animate_panes(COLLAPSED_RATIO, CHAT_EXPANDED_RATIO)

    def reset_split(self):
        self.app.editor_expanded = False
        self.app.chat_expanded = False
        self._animate_panes(DEFAULT_RATIO, DEFAULT_RATIO)

    def _animate_panes(self, editor_ratio: float, chat_ratio: float):
        editor = self.app.query_one("#editor-pane", Static)
        chat = self.app.query_one("#chat-pane", Static)

        total_height = self.app.size.height

        editor_height = int(total_height * editor_ratio)
        chat_height = int(total_height * chat_ratio)

        editor.animate("height", editor_height, duration=0.4, easing="out_cubic")
        chat.animate("height", chat_height, duration=0.4, easing="out_cubic")


# ───────────────────────────────────────────────────────────────
#  DRAGGABLE DIVIDERS
# ───────────────────────────────────────────────────────────────

class DividerController:
    """
    Handles dragging of vertical and horizontal dividers.
    Allows resizing of left/right panes and editor/chat panes.
    """
    def __init__(self, app: "LumaxTerminalIDE"):
        self.app = app
        self.dragging_vertical = False
        self.dragging_horizontal = False

    # ───────────────────────────────────────────────────────────
    #  Vertical divider (left/right)
    # ───────────────────────────────────────────────────────────

    def start_vertical_drag(self):
        self.dragging_vertical = True

    def stop_vertical_drag(self):
        self.dragging_vertical = False

    def drag_vertical(self, x: int):
        if not self.dragging_vertical:
            return

        width = self.app.size.width
        left_ratio = max(0.20, min(0.80, x / width))

        left = self.app.query_one("#left-pane", Vertical)
        right = self.app.query_one("#right-pane", Vertical)

        left.styles.width = f"{int(left_ratio * 100)}%"
        right.styles.width = f"{int((1 - left_ratio) * 100)}%"

    # ───────────────────────────────────────────────────────────
    #  Horizontal divider (editor/chat)
    # ───────────────────────────────────────────────────────────

    def start_horizontal_drag(self):
        self.dragging_horizontal = True

    def stop_horizontal_drag(self):
        self.dragging_horizontal = False

    def drag_horizontal(self, y: int):
        if not self.dragging_horizontal:
            return

        height = self.app.size.height
        editor_ratio = max(0.15, min(0.85, y / height))
        chat_ratio = 1 - editor_ratio

        editor = self.app.query_one("#editor-pane", Static)
        chat = self.app.query_one("#chat-pane", Static)

        editor.styles.height = f"{int(editor_ratio * 100)}%"
        chat.styles.height = f"{int(chat_ratio * 100)}%"


# ───────────────────────────────────────────────────────────────
#  INTEGRATION INTO MAIN APP
# ───────────────────────────────────────────────────────────────

def _install_controllers(self: "LumaxTerminalIDE"):
    """Attach controllers to the app instance."""
    self.panes = PaneController(self)
    self.dividers = DividerController(self)


LumaxTerminalIDE._install_controllers = _install_controllers


# ───────────────────────────────────────────────────────────────
#  MOUSE EVENT HANDLING FOR DRAGGING
# ───────────────────────────────────────────────────────────────

def _mouse_handlers(self: "LumaxTerminalIDE"):

    def on_mouse_down(event: events.MouseDown):
        if event.target.id == "divider-vertical":
            self.dividers.start_vertical_drag()
        elif event.target.id == "divider-horizontal":
            self.dividers.start_horizontal_drag()

    def on_mouse_up(event: events.MouseUp):
        self.dividers.stop_vertical_drag()
        self.dividers.stop_horizontal_drag()

    def on_mouse_move(event: events.MouseMove):
        if self.dividers.dragging_vertical:
            self.dividers.drag_vertical(event.x)
        if self.dividers.dragging_horizontal:
            self.dividers.drag_horizontal(event.y)

    self.on_mouse_down = on_mouse_down
    self.on_mouse_up = on_mouse_up
    self.on_mouse_move = on_mouse_move


LumaxTerminalIDE._mouse_handlers = _mouse_handlers


# ───────────────────────────────────────────────────────────────
#  CLICK HANDLERS FOR EXPANSION
# ───────────────────────────────────────────────────────────────

def _click_handlers(self: "LumaxTerminalIDE"):

    def on_click(event: events.Click):
        if event.target.id == "editor-pane":
            self.panes.expand_editor()
        elif event.target.id == "chat-pane":
            self.panes.expand_chat()

    self.on_click = on_click


LumaxTerminalIDE._click_handlers = _click_handlers


# ───────────────────────────────────────────────────────────────
#  CHUNK 4 — LM Studio + Ollama + Cloud Backends + XRL Compression
# ───────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────
#  BACKEND CONFIGURATION
# ───────────────────────────────────────────────────────────────

class BackendConfig:
    """
    Stores all backend settings for LM Studio, Ollama, Cloud, and XRL.
    """
    def __init__(self):
        self.backend = "lmstudio"  # lmstudio | ollama | cloud
        self.model = "default"

        # LM Studio (OpenAI-compatible)
        self.lmstudio_url = "http://localhost:1234/v1/chat/completions"

        # Ollama
        self.ollama_url = "http://localhost:11434/api/generate"

        # Cloud (OpenAI-compatible)
        self.cloud_url = "https://api.example.com/v1/chat/completions"
        self.api_key = ""

        # XRL compression
        self.xrl_enabled = False
        self.xrl_url = "http://localhost:9000/compress"

    def to_dict(self):
        return {
            "backend": self.backend,
            "model": self.model,
            "lmstudio_url": self.lmstudio_url,
            "ollama_url": self.ollama_url,
            "cloud_url": self.cloud_url,
            "api_key": self.api_key,
            "xrl_enabled": self.xrl_enabled,
            "xrl_url": self.xrl_url,
        }

    def from_dict(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)


# ───────────────────────────────────────────────────────────────
#  BACKEND CLIENT
# ───────────────────────────────────────────────────────────────

class BackendClient:
    """
    Unified interface for LM Studio, Ollama, Cloud, and XRL compression.
    """
    def __init__(self, config: BackendConfig):
        self.config = config

    # ───────────────────────────────────────────────────────────
    #  XRL COMPRESSION
    # ───────────────────────────────────────────────────────────

    def compress_xrl(self, text: str) -> str:
        if not self.config.xrl_enabled:
            return text

        try:
            resp = requests.post(
                self.config.xrl_url,
                json={"text": text},
                timeout=10
            )
            data = resp.json()
            return data.get("compressed", text)
        except Exception as e:
            return f"[XRL error: {e}]"

    # ───────────────────────────────────────────────────────────
    #  MAIN CALL ENTRY POINT
    # ───────────────────────────────────────────────────────────

    def call(self, prompt: str) -> str:
        """
        Compress prompt via XRL (if enabled), then call selected backend.
        """
        prompt = self.compress_xrl(prompt)

        if self.config.backend == "lmstudio":
            return self._call_lmstudio(prompt)
        elif self.config.backend == "ollama":
            return self._call_ollama(prompt)
        else:
            return self._call_cloud(prompt)

    # ───────────────────────────────────────────────────────────
    #  LM STUDIO BACKEND
    # ───────────────────────────────────────────────────────────

    def _call_lmstudio(self, prompt: str) -> str:
        try:
            resp = requests.post(
                self.config.lmstudio_url,
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[LM Studio error: {e}]"

    # ───────────────────────────────────────────────────────────
    #  OLLAMA BACKEND
    # ───────────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        try:
            resp = requests.post(
                self.config.ollama_url,
                json={"model": self.config.model, "prompt": prompt},
                timeout=30,
                stream=True,
            )

            output = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                obj = json.loads(line.decode("utf-8"))
                output += obj.get("response", "")

            return output

        except Exception as e:
            return f"[Ollama error: {e}]"

    # ───────────────────────────────────────────────────────────
    #  CLOUD BACKEND (OpenAI-compatible)
    # ───────────────────────────────────────────────────────────

    def _call_cloud(self, prompt: str) -> str:
        try:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            resp = requests.post(
                self.config.cloud_url,
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers=headers,
                timeout=30,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            return f"[Cloud error: {e}]"


# ───────────────────────────────────────────────────────────────
#  CHUNK 5 — Tools: File Tree, Diff Viewer, Logs, Settings ModalScreen,
#                 Model Selector, Command Palette
# ───────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────
#  FILE TREE
# ───────────────────────────────────────────────────────────────

class FileTree(Tree):
    """Displays directory structure and allows file selection."""
    def on_mount(self) -> None:
        self.root.expand()
        self.load_directory(Path("."))

    def load_directory(self, path: Path):
        self.root.label = str(path)
        self.root.data = path

        for item in sorted(path.iterdir()):
            node = self.root.add(str(item.name))
            node.data = item


# ───────────────────────────────────────────────────────────────
#  DIFF VIEWER
# ───────────────────────────────────────────────────────────────

class DiffViewer(RichLog):
    """Simple line-based diff viewer."""
    def on_mount(self) -> None:
        self.border_title = "Diff"

    def show_diff(self, old: str, new: str):
        self.clear()
        hdr1 = Text("[Diff preview]\n", style="yellow")
        self.write(hdr1)
        hdr2 = Text("--- old\n+++ new\n", style="grey")
        self.write(hdr2)

        old_lines = old.splitlines()
        new_lines = new.splitlines()

        for line in old_lines:
            if line not in new_lines:
                old_line = Text(f"- {line}", style="red")
                self.write(old_line)

        for line in new_lines:
            if line not in old_lines:
                new_line = Text(f"+ {line}", style="green")
                self.write(new_line)


# ───────────────────────────────────────────────────────────────
#  LOGS PANE
# ───────────────────────────────────────────────────────────────

class LogsPane(RichLog):
    """General logging output."""
    def on_mount(self) -> None:
        self.border_title = "Logs"
        self.write("Lumax IDE Logs Initialized.\n")


# ───────────────────────────────────────────────────────────────
#  SETTINGS ModalScreen
# ───────────────────────────────────────────────────────────────

class SettingsModal(ModalScreen):
    """Settings for backend configuration."""
    def __init__(self, config: BackendConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Label("Settings", id="settings-title")

        yield Label("Backend (lmstudio / ollama / cloud):")
        yield Input(self.config.backend, id="backend-input")

        yield Label("Model name:")
        yield Input(self.config.model, id="model-name")

        yield Label("LM Studio URL:")
        yield Input(self.config.lmstudio_url, id="lmstudio-url")

        yield Label("Ollama URL:")
        yield Input(self.config.ollama_url, id="ollama-url")

        yield Label("Cloud URL:")
        yield Input(self.config.cloud_url, id="cloud-url")

        yield Label("API Key:")
        yield Input(self.config.api_key, password=True, id="api-key")

        yield Label("XRL enabled (true/false):")
        yield Input(str(self.config.xrl_enabled).lower(), id="xrl-enabled")

        yield Label("XRL URL:")
        yield Input(self.config.xrl_url, id="xrl-url")

        yield Button("Save", id="settings-save")
        yield Button("Close", id="settings-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("settings-close", "settings-save"):
            self.app.pop_screen()


# ───────────────────────────────────────────────────────────────
#  MODEL SELECTOR ModalScreen
# ───────────────────────────────────────────────────────────────

class ModelSelectorModal(ModalScreen):
    """Lists available models for LM Studio or Ollama."""
    def __init__(self, config: BackendConfig):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Label("Model Selector", id="model-selector-title")

        # Placeholder — real model listing will be added in Chunk 6
        yield Label("Enter model name manually:")
        yield Input(self.config.model, id="model-selector-input")

        yield Button("Apply", id="model-selector-apply")
        yield Button("Close", id="model-selector-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("model-selector-close", "model-selector-apply"):
            self.app.pop_screen()


# ───────────────────────────────────────────────────────────────
#  COMMAND PALETTE
# ───────────────────────────────────────────────────────────────

class CommandPalette(ModalScreen):
    """Quick command launcher."""
    def compose(self) -> ComposeResult:
        yield Label("Command Palette (type a command):")
        yield Input(id="command-input")
        yield Button("Run", id="command-run")
        yield Button("Close", id="command-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("command-close", "command-run"):
            self.app.pop_screen()

if __name__ == "__main__":
    app = LumaxTerminalIDE()
    app.run()
