import asyncio
import base64
import copy
import hashlib
import json
import logging
import os
import secrets
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from feature_inventory_parser import parse_feature_inventory_markdown
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

# Configure Logging (routine request logs: uvicorn access_log off by default)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
logger = logging.getLogger("WebAppBridge")


def _uvicorn_log_level() -> str:
    raw = (
        os.getenv("FoveAI_UVICORN_LOG_LEVEL", os.getenv("LOG_LEVEL", "WARNING"))
        .strip()
        .upper()
    )
    m = {
        "CRITICAL": "critical",
        "ERROR": "error",
        "WARNING": "warning",
        "INFO": "info",
        "DEBUG": "debug",
        "TRACE": "trace",
    }
    return m.get(raw, "warning")


def _uvicorn_access_log() -> bool:
    return os.getenv("FoveAI_UVICORN_ACCESS_LOG", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# --- Web UI gate ---
# Production / Docker: set FoveAI_WEBUI_PASSWORD (see docker-compose foveai_ops).
# Local dev without a password: FoveAI_WEBUI_ALLOW_INSECURE=1 (never on public networks).
WEBUI_PASSWORD = os.getenv("FoveAI_WEBUI_PASSWORD", "").strip()
WEBUI_SESSION_SECRET = os.getenv("FoveAI_WEBUI_SESSION_SECRET", "").strip()
WEBUI_ALLOW_INSECURE = os.getenv(
    "FoveAI_WEBUI_ALLOW_INSECURE", "0"
).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
SESSION_KEY_OK = "foveai_webui_ok"


def _validate_webui_auth_config() -> None:
    """Require a non-empty password unless FoveAI_WEBUI_ALLOW_INSECURE=1 (dev-only)."""
    if WEBUI_PASSWORD:
        return
    if WEBUI_ALLOW_INSECURE:
        return
    raise RuntimeError(
        "FoveAI_WEBUI_PASSWORD is empty. Set it in the environment (e.g. .env next to docker-compose), "
        "or set FoveAI_WEBUI_ALLOW_INSECURE=1 for local development only (no password gate)."
    )


def _webui_session_secret() -> str:
    if WEBUI_SESSION_SECRET:
        return WEBUI_SESSION_SECRET
    if WEBUI_PASSWORD:
        return hashlib.sha256(("foveai-webui|" + WEBUI_PASSWORD).encode()).hexdigest()
    return "foveai-webui-dev-insecure-fixed-do-not-use-in-production"


@asynccontextmanager
async def _webui_lifespan(_app: FastAPI):
    _validate_webui_auth_config()
    _p = {getattr(r, "path", None) for r in _app.routes if hasattr(r, "path")}
    if "/api/feature_inventory" not in _p and "/api/fmap" not in _p:
        logger.error(
            "web_app startup: feature map routes missing from app.routes (have %s total path routes)",
            len([x for x in _p if x]),
        )
    yield


app = FastAPI(title="Lumax Web App Bridge", lifespan=_webui_lifespan)
# Session cookie: one login until max_age (or secret change). SameSite=Lax, path=/ for all /api routes.
# Same host for every visit or the cookie will not apply:
#   - localhost vs 127.0.0.1 are different origins.
#   - Raw LAN IPs (192.168.x.x) are each their own origin; if DHCP gives the PC a new IP, that URL
#     changes and you must sign in again. Prefer a stable name: router DHCP reservation + fixed IP,
#     or use http://<PC-hostname>.local:8080 (mDNS) / your LAN DNS name so the URL stays the same
#     when the address behind it changes.
app.add_middleware(
    SessionMiddleware,
    secret_key=_webui_session_secret(),
    max_age=int(os.getenv("FoveAI_WEBUI_SESSION_MAX_AGE", str(7 * 24 * 3600))),
    same_site="lax",
    https_only=False,
    path="/",
    session_cookie=os.getenv("FoveAI_WEBUI_SESSION_COOKIE", "foveai_webui_session"),
)
# Outermost: fix client scheme/host when behind nginx/Traefik (X-Forwarded-*) so Chatterbox iframe URLs match the browser.
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
except ImportError:
    pass

# Optional: comma-separated origins for Capacitor / Vite dev / other LAN shells (session cookies need allow_credentials).
_FoveAI_WEBUI_CORS_ORIGINS = os.getenv("FoveAI_WEBUI_CORS_ORIGINS", "").strip()
if _FoveAI_WEBUI_CORS_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    _cors_list = [o.strip() for o in _FoveAI_WEBUI_CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


class LoginBody(BaseModel):
    password: str = Field("", max_length=4096)


async def require_webui_login(request: Request) -> None:
    """Require a prior successful POST /api/auth/login when a password is configured."""
    if not WEBUI_PASSWORD:
        return
    if request.session.get(SESSION_KEY_OK):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")


@app.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, Any]:
    if not WEBUI_PASSWORD:
        return {"auth_required": False, "authenticated": True, "insecure": True}
    return {
        "auth_required": True,
        "authenticated": bool(request.session.get(SESSION_KEY_OK)),
        "insecure": False,
    }


def _password_matches(given: str) -> bool:
    try:
        return secrets.compare_digest(WEBUI_PASSWORD, given)
    except (TypeError, ValueError):
        return False


@app.post("/api/auth/login")
async def auth_login(request: Request, body: LoginBody) -> dict[str, bool]:
    if not WEBUI_PASSWORD:
        request.session[SESSION_KEY_OK] = True
        return {"ok": True}
    if not _password_matches(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    request.session[SESSION_KEY_OK] = True
    return {"ok": True}


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Lightweight liveness for foveai_ops / AutonomousSentry (no login; keep port 8080 off public networks)."""
    paths = {getattr(r, "path", "") for r in app.routes if hasattr(r, "path")}
    return {
        "status": "ok",
        "service": "foveai_webui",
        "web_app_file": str(Path(__file__).resolve()),
        # Confirms this process includes TTS proxy + GPU switch (if missing, Web UI image/volume is stale).
        "tts_routes": {
            "GET_PUT": "/api/tts/backend",
            "POST": "/api/tts/gpu_stack",
        },
        "feature_map_ok": "/api/feature_inventory" in paths or "/api/fmap" in paths,
    }


# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANNOUNCEMENTS_PATH = os.path.join(BASE_DIR, "announcements.json")
UI_CONFIG_PATH = os.getenv(
    "FoveAI_UI_CONFIG_PATH", os.path.join(BASE_DIR, "foveai_ui_config.json")
)
LEGACY_BRANDING_PATH = os.path.join(BASE_DIR, "webui_branding.json")
SOUL_URL = os.getenv("SOUL_URL", "http://foveai_soul:8402").rstrip("/")
EARS_URL = os.getenv("EARS_URL", "http://foveai_ears:8001").rstrip("/")
MOUTH_URL = os.getenv("MOUTH_URL", "http://foveai_body:8002").rstrip("/")
CREATIVE_URL = os.getenv(
    "CREATIVE_SERVICE_URL", "http://foveai_creativity:8003"
).rstrip("/")
TURBO_URL = os.getenv("TURBO_URL", "http://foveai_turbochat:8005").rstrip("/")
CHATTERBOX_INTERNAL_URL = os.getenv(
    "FoveAI_CHATTERBOX_HTTP_URL", "http://foveai_chatterbox_resemble:8004"
).rstrip("/")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://foveai_ollama_backup:11434").rstrip("/")
_FoveAI_DREAM_PROXY_TIMEOUT = float(os.getenv("FoveAI_DREAM_PROXY_TIMEOUT_SEC", "600"))
_WEBUI_PORT = int(os.getenv("WEBUI_PORT", "8080"))

# Minimal WAV (silence) for diagnostics pipeline — same idea as tests/smoke_stt_thinking_tts.py
_PIPELINE_DUMMY_WAV_B64 = base64.b64encode(
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x44\xac\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
).decode("ascii")
_SOUL_PIPELINE_ERR_MARKERS = (
    "cognition error",
    "error:",
    "exceed context",
    "context window",
)

_feature_inventory_cache: tuple[str, float, dict[str, Any]] | None = None


def _repo_root() -> str:
    """Repo root for `docker compose -f docker-compose.yml` (Docker: /app; dev: Lumax checkout)."""
    env = os.getenv("FoveAI_REPO_ROOT", "").strip()
    if env:
        return env
    # web_app.py → Frontend/Body/Webui → parents[3] = repo root
    return str(Path(__file__).resolve().parent.parent.parent.parent)


_REPO_ROOT = _repo_root()


def _feature_inventory_markdown_path() -> Path | None:
    """Resolve FEATURE_INVENTORY.md: env override, then walk up from this package (finds /app/... with bind mount)."""
    explicit = os.getenv("FoveAI_FEATURE_INVENTORY_PATH", "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p.resolve()
    here = Path(BASE_DIR).resolve()
    for anc in [here, *here.parents]:
        cand = anc / "FEATURE_INVENTORY.md"
        if cand.is_file():
            return cand.resolve()
    docker_default = Path("/app") / "FEATURE_INVENTORY.md"
    if docker_default.is_file():
        return docker_default.resolve()
    return None


def _feature_inventory_payload() -> dict[str, Any]:
    """Build JSON for Feature Map tab (cached by path + mtime)."""
    global _feature_inventory_cache
    path = _feature_inventory_markdown_path()
    if path is None:
        hint = Path(BASE_DIR).resolve()
        return {
            "ok": False,
            "error": "not_found",
            "path": "",
            "detail": (
                "FEATURE_INVENTORY.md not found. Expected at repo root next to docker-compose.yml "
                f"(searched upward from {hint}). In Docker, ensure `.:/app` mount and `/app/FEATURE_INVENTORY.md` exists. "
                "Or set FoveAI_FEATURE_INVENTORY_PATH to an absolute path inside the container."
            ),
        }
    mtime = path.stat().st_mtime
    key = str(path)
    if (
        _feature_inventory_cache is not None
        and _feature_inventory_cache[0] == key
        and _feature_inventory_cache[1] == mtime
    ):
        return {"ok": True, **_feature_inventory_cache[2]}
    text = path.read_text(encoding="utf-8")
    data = parse_feature_inventory_markdown(text)
    data["source_file"] = str(path.resolve())
    _feature_inventory_cache = (key, mtime, data)
    return {"ok": True, **data}


class GpuTtsStackBody(BaseModel):
    """Match scripts/switch_gpu_tts_stack.ps1: one GPU TTS stack at a time."""

    mode: Literal["turbo", "chatterbox_ui"]


# Shared across browser + VR: identity strings. Web-only (nav, auth, PWA) lives under "web".
GLOBAL_KEYS = frozenset({"site_name", "slogan", "ready_message"})

_BRAND_STR_MAX = 4000
_BRAND_NAV_KEYS = frozenset(
    (
        "SANCTUARY",
        "NEURAL",
        "THOUGHTS",
        "IMAGINE",
        "VISION",
        "VESSEL",
        "AGENCY",
        "SOCIAL",
        "COWORK",
        "NUCLEUS",
        "UTILS",
        "CHATTERBOX",
        "CHECKUP",
        "BRANDING",
        "FEATUREMAP",
    )
)
_BRAND_GROUP_KEYS = frozenset(
    ("cognition", "manifestation", "agency", "laboratory", "utilities")
)


def _default_branding() -> dict[str, Any]:
    return {
        "site_name": "Lumax",
        "page_title": "Lumax — Your everything for life",
        "slogan": "Your everything for life.",
        "manifest_short_name": "Lumax",
        "auth_blurb": (
            "Sign in once to unlock this console; your browser keeps the session until it expires "
            "or site data is cleared. Optional cloud features may ask you to sign in separately."
        ),
        "auth_continue_button": "Continue",
        "consent_title": "Privacy",
        "consent_body": (
            "Session and environment data may be used to improve your companion’s behavior. "
            "Treat sensitive inputs accordingly. You can stop using the UI at any time."
        ),
        "consent_button": "I understand",
        "header_status_prefix": "Godot · VR ·",
        "footer_stack": "Stack: local + optional cloud",
        "nav_groups": {
            "cognition": "Cognition",
            "manifestation": "Manifestation",
            "agency": "Agency",
            "laboratory": "Laboratory",
            "utilities": "Utilities",
        },
        "nav_tabs": {
            "SANCTUARY": "CHRONICLE",
            "NEURAL": "ETHOS (PERSONA)",
            "THOUGHTS": "LOGOS (COG)",
            "IMAGINE": "DREAMSCAPE (ART)",
            "VISION": "SPECTRAL VIEW",
            "VESSEL": "VESSEL RIG",
            "AGENCY": "AUTONOMOUS",
            "SOCIAL": "MULTIVERSE",
            "COWORK": "RATATOSK (CODE)",
            "NUCLEUS": "NUCLEUS (DEBUG)",
            "UTILS": "ANNOUNCE BOARD",
            "CHATTERBOX": "CHATTERBOX (TTS)",
            "CHECKUP": "SYSTEM CHECK",
            "BRANDING": "LABEL EDITOR",
            "FEATUREMAP": "FEATURE MAP",
        },
        "chat_placeholder": "Transmit thoughts to Jen...",
        "utils_title": "Announcements",
        "utils_blurb": (
            "Operational notices and reminders. Content is served from announcements.json "
            "next to the Web UI (editable on disk)."
        ),
        "ready_message": "Connected. Lumax Web UI is ready.",
    }


def _clamp_str(val: Any, max_len: int = _BRAND_STR_MAX) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return s[:max_len]


def _default_mobile() -> dict[str, Any]:
    """Reserved for Android / React Native / Capacitor APK — fetch GET /api/ui_config and read `mobile`."""
    return {
        "labels": {},
        "nav": {},
    }


def _default_desktop() -> dict[str, Any]:
    """Reserved for Godot/Electron desktop shell — same pattern as `godot_vr`."""
    return {
        "labels": {},
        "nav": {},
    }


def _merge_client_stub_dict(
    defaults: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Shallow merge for open-ended mobile/desktop sections."""
    out = copy.deepcopy(defaults)
    if not isinstance(overlay, dict):
        return out
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def _default_godot_vr() -> dict[str, Any]:
    return {
        "hubs": {
            "MIND": ["PSYCHE", "SOUL", "BRAINS", "MEMORY", "EMOTIONS"],
            "BODY": ["VESSEL", "AGENCY", "VITALS"],
            "MANIFEST": ["IMAGEN", "VIDGEN", "MEDIA"],
            "CORE": ["CHAT", "LOGS", "SETTINGS", "SYSTEM", "FILES"],
        },
        "ribbon_labels": {
            "MIND": "MIND",
            "BODY": "BODY",
            "MANIFEST": "MANIFEST",
            "CORE": "CORE",
        },
        "tab_labels": {},
    }


def _default_ui_config() -> dict[str, Any]:
    flat = _default_branding()
    return {
        "version": 1,
        "global": {k: flat[k] for k in GLOBAL_KEYS},
        "web": {k: flat[k] for k in flat if k not in GLOBAL_KEYS},
        "godot_vr": _default_godot_vr(),
        "mobile": _default_mobile(),
        "desktop": _default_desktop(),
    }


def _migrate_legacy_flat_to_ui_config(leg: dict[str, Any]) -> dict[str, Any]:
    g = {k: leg[k] for k in GLOBAL_KEYS if k in leg}
    w = {k: v for k, v in leg.items() if k not in GLOBAL_KEYS}
    return {
        "version": 1,
        "global": g,
        "web": w,
        "godot_vr": _default_godot_vr(),
        "mobile": _default_mobile(),
        "desktop": _default_desktop(),
    }


def _merge_godot_vr_dicts(
    defaults: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    out = copy.deepcopy(defaults)
    if not isinstance(overlay, dict):
        return out
    if isinstance(overlay.get("hubs"), dict):
        for hk, lst in overlay["hubs"].items():
            if isinstance(lst, list):
                out["hubs"][hk] = [str(x)[:64] for x in lst]
    if isinstance(overlay.get("ribbon_labels"), dict):
        for k, v in overlay["ribbon_labels"].items():
            out["ribbon_labels"][k] = _clamp_str(v, 200)
    if isinstance(overlay.get("tab_labels"), dict):
        for k, v in overlay["tab_labels"].items():
            out["tab_labels"][k] = _clamp_str(v, 200)
    return out


def _merge_ui_config_with_defaults(
    defaults: dict[str, Any], loaded: dict[str, Any]
) -> dict[str, Any]:
    out = copy.deepcopy(defaults)
    out["version"] = int(loaded.get("version", 1))
    lg = loaded.get("global")
    if isinstance(lg, dict):
        for k in GLOBAL_KEYS:
            if k in lg:
                out["global"][k] = _clamp_str(lg[k])
    lw = loaded.get("web")
    if isinstance(lw, dict) and len(lw) > 0:
        def_flat = _default_branding()
        merged_web: dict[str, Any] = copy.deepcopy(out["web"])
        for k, v in lw.items():
            if k == "nav_groups" and isinstance(v, dict):
                g = dict(merged_web.get("nav_groups") or def_flat["nav_groups"])
                for gk, gv in v.items():
                    if gk in _BRAND_GROUP_KEYS:
                        g[gk] = _clamp_str(gv, 500)
                merged_web["nav_groups"] = g
            elif k == "nav_tabs" and isinstance(v, dict):
                t = dict(merged_web.get("nav_tabs") or def_flat["nav_tabs"])
                for tk, tv in v.items():
                    if tk in _BRAND_NAV_KEYS:
                        t[tk] = _clamp_str(tv, 500)
                merged_web["nav_tabs"] = t
            elif k in def_flat and k not in ("nav_groups", "nav_tabs"):
                merged_web[k] = _clamp_str(v)
        out["web"] = merged_web
    out["godot_vr"] = _merge_godot_vr_dicts(
        defaults["godot_vr"], loaded.get("godot_vr") or {}
    )
    out["mobile"] = _merge_client_stub_dict(
        out.get("mobile") or _default_mobile(),
        loaded.get("mobile") or {},
    )
    out["desktop"] = _merge_client_stub_dict(
        out.get("desktop") or _default_desktop(),
        loaded.get("desktop") or {},
    )
    return out


def _load_ui_config() -> dict[str, Any]:
    d = _default_ui_config()
    if os.path.isfile(UI_CONFIG_PATH):
        try:
            with open(UI_CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                d = _merge_ui_config_with_defaults(d, loaded)
        except Exception as e:
            logger.warning("foveai_ui_config.json unreadable: %s", e)
    elif os.path.isfile(LEGACY_BRANDING_PATH):
        try:
            with open(LEGACY_BRANDING_PATH, "r", encoding="utf-8") as f:
                leg = json.load(f)
            if isinstance(leg, dict) and "version" not in leg:
                d = _migrate_legacy_flat_to_ui_config(leg)
                _save_ui_config(d)
                logger.info(
                    "Migrated %s to unified %s", LEGACY_BRANDING_PATH, UI_CONFIG_PATH
                )
        except Exception as e:
            logger.warning("legacy webui_branding.json unreadable: %s", e)
    return d


def _save_ui_config(cfg: dict[str, Any]) -> None:
    parent = os.path.dirname(UI_CONFIG_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(UI_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _effective_web_flat(cfg: dict[str, Any]) -> dict[str, Any]:
    """Flatten global + web layers for the browser (backward-compatible /api/branding)."""
    base = _default_branding()
    g = cfg.get("global") or {}
    w = cfg.get("web") or {}
    for k in GLOBAL_KEYS:
        if k in g:
            base[k] = _clamp_str(g[k])
    defaults = _default_branding()
    for k, v in w.items():
        if k == "nav_groups" and isinstance(v, dict):
            merged = dict(base["nav_groups"])
            for gk, gv in v.items():
                if gk in _BRAND_GROUP_KEYS:
                    merged[gk] = _clamp_str(gv, 500)
            base["nav_groups"] = merged
        elif k == "nav_tabs" and isinstance(v, dict):
            merged = dict(base["nav_tabs"])
            for tk, tv in v.items():
                if tk in _BRAND_NAV_KEYS:
                    merged[tk] = _clamp_str(tv, 500)
            base["nav_tabs"] = merged
        elif k in defaults and k not in ("nav_groups", "nav_tabs"):
            base[k] = _clamp_str(v)
    return base


def _merge_flat_patch_into_ui_config(
    cfg: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    out = copy.deepcopy(cfg)
    g = dict(out.get("global") or {})
    w = dict(out.get("web") or {})
    def_flat = _default_branding()
    for k, v in patch.items():
        if k in GLOBAL_KEYS:
            g[k] = _clamp_str(v)
        elif k == "nav_groups" and isinstance(v, dict):
            cur = dict(w.get("nav_groups") or def_flat["nav_groups"])
            for gk, gv in v.items():
                if gk in _BRAND_GROUP_KEYS:
                    cur[gk] = _clamp_str(gv, 500)
            w["nav_groups"] = cur
        elif k == "nav_tabs" and isinstance(v, dict):
            cur = dict(w.get("nav_tabs") or def_flat["nav_tabs"])
            for tk, tv in v.items():
                if tk in _BRAND_NAV_KEYS:
                    cur[tk] = _clamp_str(tv, 500)
            w["nav_tabs"] = cur
        elif k in def_flat and k not in ("nav_groups", "nav_tabs"):
            w[k] = _clamp_str(v)
    out["global"] = g
    out["web"] = w
    out["version"] = 1
    return out


def _load_branding() -> dict[str, Any]:
    return _effective_web_flat(_load_ui_config())


_DEFAULT_ANNOUNCEMENTS = {
    "items": [
        {
            "date": "2026-04-07",
            "tag": "NAME",
            "title": "Why Lumax?",
            "body": "Lumax is Lumen Maximum—light turned all the way up. Your everything for life: “your” anchors it in one person; “everything” refuses a thin category—we mean companion and agent together, the full arc. The line is also meant to breathe: a little poetic, life-giving in the sense of support that sustains and enlivens, not only performs. The sound sits next to my nickname, Lumba—same opening, grown into a name built to outlast a single person.",
            "priority": "info",
        },
        {
            "date": "2026-04-07",
            "tag": "NETWORK",
            "title": "Tailscale + Cloudflare",
            "body": "Subnet router on the always-on box; public entry via Cloudflare Tunnel when needed. See ops notes.",
            "priority": "info",
        },
        {
            "date": "2026-04-07",
            "tag": "UI",
            "title": "Announce board",
            "body": "Edit Frontend/Body/Webui/announcements.json to post vessel-wide bulletins.",
            "priority": "ops",
        },
    ]
}


def _load_announcements():
    if os.path.isfile(ANNOUNCEMENTS_PATH):
        try:
            with open(ANNOUNCEMENTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except Exception as e:
            logger.warning("announcements.json unreadable: %s", e)
    return dict(_DEFAULT_ANNOUNCEMENTS)


@app.get("/", response_class=HTMLResponse)
async def get_index() -> FileResponse:
    """Serve shell HTML; avoid stale copies in the browser after `git pull` or local edits."""
    return FileResponse(
        os.path.join(BASE_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/manifest.json")
async def get_manifest():
    b = _load_branding()
    return {
        "name": b.get("page_title") or "Lumax",
        "short_name": b.get("manifest_short_name") or "Lumax",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#02050a",
        "theme_color": "#00f3ff",
        "icons": [
            {
                "src": "https://img.icons8.com/neon/512/artificial-intelligence.png",
                "sizes": "512x512",
                "type": "image/png",
            }
        ],
    }


@app.get("/api/branding")
async def get_branding() -> dict[str, Any]:
    """Public read so the login screen and shell can show custom names before auth."""
    return _load_branding()


@app.put("/api/branding")
async def put_branding(
    body: dict[str, Any] = Body(...),
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    cfg = _load_ui_config()
    cfg = _merge_flat_patch_into_ui_config(cfg, body)
    _save_ui_config(cfg)
    return _effective_web_flat(cfg)


@app.get("/api/ui_config")
async def get_ui_config() -> dict[str, Any]:
    """Unified UI: global + per-client sections (web, godot_vr, mobile, desktop). Public read on LAN."""
    cfg = _load_ui_config()
    return {
        "version": cfg.get("version", 1),
        "global": cfg.get("global") or {},
        "web": cfg.get("web") or {},
        "godot_vr": cfg.get("godot_vr") or _default_godot_vr(),
        "mobile": cfg.get("mobile") or _default_mobile(),
        "desktop": cfg.get("desktop") or _default_desktop(),
        "effective_web": _effective_web_flat(cfg),
    }


@app.post("/api/chat")
async def proxy_chat(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{SOUL_URL}/compagent", json=data)
        return resp.json()


@app.post("/api/stt")
async def proxy_stt(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{EARS_URL}/stt", json=data)
        return resp.json()


@app.get("/api/announcements")
async def get_announcements(_auth: None = Depends(require_webui_login)):
    """Bulletins for the Web UI Utils → Announce Board tab."""
    return _load_announcements()


@app.get("/api/vitals")
async def proxy_vitals(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{SOUL_URL}/vitals")
        return resp.json()


@app.get("/api/soul/dna")
async def proxy_get_soul_dna(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/soul_dna")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/update_soul")
async def proxy_update_soul(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SOUL_URL}/update_soul", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/soul/runtime_status")
async def proxy_soul_runtime_status(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{SOUL_URL}/soul_runtime_status")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/soul/ps")
async def proxy_soul_ps(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/ps")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/soul/switch_model")
async def proxy_soul_switch_model(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{SOUL_URL}/switch_model", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/soul/runtime_config")
async def proxy_soul_runtime_config(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{SOUL_URL}/soul_runtime_config", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


# ── Autonomous Agent Proxy Routes ────────────────────────────────────────
# Forward /api/agent/* from WebUI (port 8080) to XRLF runtime (port 8402)
# so the Agency Tab START/STOP buttons and status polling work from the browser.


@app.get("/api/agent/status")
async def proxy_agent_status(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/status")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/start")
async def proxy_agent_start(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/start")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/stop")
async def proxy_agent_stop(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/stop")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/messages")
async def proxy_agent_messages(
    limit: int = 20, _auth: None = Depends(require_webui_login)
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SOUL_URL}/api/agent/messages", params={"limit": limit}
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/messages/mark")
async def proxy_agent_mark_messages(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/messages/mark", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/plans")
async def proxy_agent_plans(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/plans")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/thoughts")
async def proxy_agent_thoughts(
    limit: int = 20, _auth: None = Depends(require_webui_login)
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SOUL_URL}/api/agent/thoughts", params={"limit": limit}
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/actions")
async def proxy_agent_actions(
    limit: int = 20, _auth: None = Depends(require_webui_login)
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SOUL_URL}/api/agent/actions", params={"limit": limit}
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/context")
async def proxy_agent_context(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/context")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/message")
async def proxy_agent_enqueue_message(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/message", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/plan")
async def proxy_agent_create_plan(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/plan", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/plan/{plan_id}")
async def proxy_agent_get_plan(
    plan_id: str, _auth: None = Depends(require_webui_login)
):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/plan/{plan_id}")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/memory/{key}")
async def proxy_agent_get_memory(key: str, _auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/memory/{key}")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.post("/api/agent/memory")
async def proxy_agent_set_memory(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SOUL_URL}/api/agent/memory", json=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


@app.get("/api/agent/queue/stats")
async def proxy_agent_queue_stats(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SOUL_URL}/api/agent/queue/stats")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code, detail=(resp.text or "")[:2000]
            )
        return resp.json()


async def _fetch_creativity_health(
    client: httpx.AsyncClient,
) -> tuple[dict[str, Any] | None, str | None, str | None, int | None]:
    """Try GET /health then GET /api/health on foveai_creativity.

    Returns (json_or_none, error_text_or_none, resolved_url_or_none, last_http_status).
    """
    last_err: str | None = None
    last_code: int | None = None
    for path in ("/health", "/api/health"):
        url = f"{CREATIVE_URL}{path}"
        try:
            resp = await client.get(url)
        except Exception as e:
            last_err = str(e)
            last_code = None
            continue
        last_code = resp.status_code
        last_err = (resp.text or "")[:2000]
        if resp.status_code == 200:
            try:
                return resp.json(), None, url, 200
            except Exception:
                continue
    return None, last_err, None, last_code


@app.get("/api/creativity/status")
async def proxy_creativity_status(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get(f"{CREATIVE_URL}/openapi.json")
        except Exception as e:
            return {"ok": False, "url": CREATIVE_URL, "detail": str(e)}
        out: dict[str, Any] = {
            "ok": resp.status_code == 200,
            "url": CREATIVE_URL,
            "status_code": resp.status_code,
        }
        health_json, health_err, health_url, _hc = await _fetch_creativity_health(
            client
        )
        if health_json is not None:
            out["health"] = health_json
            if health_url:
                out["health_url"] = health_url
        else:
            out["health"] = None
            out["health_error"] = (
                health_err or "GET /health and /api/health failed on creativity service"
            )
    return out


@app.get("/api/creativity/health")
async def proxy_creativity_health(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    """Model paths and SDXL / SD1.4 ONNX hints from foveai_creativity GET /health."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        health_json, err_text, _url, last_code = await _fetch_creativity_health(client)
    if health_json is not None:
        return health_json
    return {
        "status": "error",
        "url": f"{CREATIVE_URL}/health",
        "detail": err_text or "no response",
        "upstream_status_code": last_code,
    }


@app.get("/api/dream/catalog")
async def proxy_dream_catalog(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{CREATIVE_URL}/api/dream/catalog")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code, detail=(resp.text or "")[:2000]
        )
    return resp.json()


@app.post("/api/dream")
async def proxy_dream(request: Request, _auth: None = Depends(require_webui_login)):
    data = await request.json()
    async with httpx.AsyncClient(timeout=_FoveAI_DREAM_PROXY_TIMEOUT) as client:
        resp = await client.post(f"{CREATIVE_URL}/api/dream", json=data)
    ct = resp.headers.get("content-type", "application/json")
    return Response(content=resp.content, status_code=resp.status_code, media_type=ct)


def _diagnostic_probe_specs() -> list[tuple[str, str, str, bool]]:
    """(id, label, url, optional_soft_fail)."""
    webui_self = f"http://127.0.0.1:{_WEBUI_PORT}/health"
    return [
        ("webui", "Web UI (this process)", webui_self, False),
        ("soul", "Soul (compagent)", f"{SOUL_URL}/health", False),
        ("ears", "Ears (STT)", f"{EARS_URL}/health", False),
        ("mouth", "Mouth (TTS router)", f"{MOUTH_URL}/health", False),
        ("creative", "Creativity (dream)", f"{CREATIVE_URL}/health", False),
        ("turbo", "Turbo XTTS (GPU stack)", f"{TURBO_URL}/health", True),
        (
            "chatterbox",
            "Chatterbox (Resemble API)",
            f"{CHATTERBOX_INTERNAL_URL}/openapi.json",
            True,
        ),
        ("ollama", "Ollama", f"{OLLAMA_HOST}/api/tags", True),
    ]


async def _diagnostic_probe_one(
    client: httpx.AsyncClient,
    check_id: str,
    label: str,
    url: str,
    optional: bool,
) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        resp = await client.get(url)
        ms = int((time.monotonic() - t0) * 1000)
        ok = resp.status_code == 200
        detail = f"HTTP {resp.status_code} ({ms}ms)"
        if not ok:
            tail = (resp.text or "")[:280].replace("\n", " ")
            if tail:
                detail += f" — {tail}"
        return {
            "id": check_id,
            "label": label,
            "ok": ok,
            "detail": detail,
            "optional": optional,
            "url": url,
        }
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        return {
            "id": check_id,
            "label": label,
            "ok": False,
            "detail": f"{type(e).__name__}: {e} ({ms}ms)",
            "optional": optional,
            "url": url,
        }


class DiagnosticRunBody(BaseModel):
    ids: list[str] | None = None


class DiagnosticsTtsBody(BaseModel):
    text: str = Field(default="Lumax voice check.", max_length=4096)
    voice: str | None = Field(default=None, max_length=512)
    engine: str = Field(default="TURBO", max_length=64)


async def _run_diagnostics(ids: list[str] | None) -> dict[str, Any]:
    specs = _diagnostic_probe_specs()
    want = set(ids) if ids else None
    to_run = [s for s in specs if want is None or s[0] in want]
    async with httpx.AsyncClient(timeout=12.0) as client:
        coros = [
            _diagnostic_probe_one(client, cid, label, url, opt)
            for cid, label, url, opt in to_run
        ]
        results = await asyncio.gather(*coros) if coros else []
    return {"results": list(results), "ts": time.time()}


@app.get("/api/diagnostics/checks")
async def diagnostics_checks(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    specs = _diagnostic_probe_specs()
    return {
        "checks": [{"id": s[0], "label": s[1], "optional": s[3]} for s in specs],
    }


@app.get("/api/diagnostics/run")
async def diagnostics_run_get(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    return await _run_diagnostics(None)


@app.post("/api/diagnostics/run")
async def diagnostics_run_post(
    body: DiagnosticRunBody = Body(default=DiagnosticRunBody()),
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    ids = body.ids if body.ids else None
    return await _run_diagnostics(ids)


@app.post("/api/diagnostics/pipeline")
async def diagnostics_pipeline(
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    """
    End-to-end: EARS STT (tiny WAV) → soul /compagent → Mouth TTS (TURBO).
    Same spirit as tests/smoke_stt_thinking_tts.py from the Web UI bridge.
    Does not run Godot / XR / guardian (that stays on the host: AUTOTEST_Lumax_current.ps1).
    """
    steps: list[dict[str, Any]] = []
    soul_input = "Reply with exactly one word: pong."

    async with httpx.AsyncClient() as client:
        t0 = time.monotonic()
        try:
            r_stt = await client.post(
                f"{EARS_URL}/stt",
                json={"audio_base64": _PIPELINE_DUMMY_WAV_B64},
                timeout=120.0,
            )
            ms = int((time.monotonic() - t0) * 1000)
            if r_stt.status_code != 200:
                steps.append(
                    {
                        "id": "stt",
                        "ok": False,
                        "detail": f"HTTP {r_stt.status_code}",
                        "ms": ms,
                    }
                )
                return {
                    "ok": False,
                    "steps": steps,
                    "note": "pipeline_stopped_after_stt",
                }
            stt_body = r_stt.json()
            tr = (stt_body.get("text") or "").strip()
            used_fallback = not tr or tr.startswith("[")
            if not used_fallback:
                soul_input = tr[:2000]
            steps.append(
                {
                    "id": "stt",
                    "ok": True,
                    "detail": (
                        "empty transcript → default prompt"
                        if used_fallback
                        else f"transcript {len(tr)} chars"
                    ),
                    "ms": ms,
                }
            )
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(
                {
                    "id": "stt",
                    "ok": False,
                    "detail": f"{type(e).__name__}: {e}",
                    "ms": ms,
                }
            )
            return {"ok": False, "steps": steps, "note": "pipeline_stopped_after_stt"}

        t0 = time.monotonic()
        try:
            r_soul = await client.post(
                f"{SOUL_URL}/compagent",
                json={
                    "input": soul_input,
                    "session_id": "webui_diag_pipeline",
                    "skip_features": True,
                },
                timeout=300.0,
            )
            ms = int((time.monotonic() - t0) * 1000)
            if r_soul.status_code != 200:
                steps.append(
                    {
                        "id": "soul",
                        "ok": False,
                        "detail": f"HTTP {r_soul.status_code}",
                        "ms": ms,
                    }
                )
                return {
                    "ok": False,
                    "steps": steps,
                    "note": "pipeline_stopped_after_soul",
                }
            soul = r_soul.json()
            reply = (soul.get("response") or "").strip()
            if not reply:
                steps.append(
                    {"id": "soul", "ok": False, "detail": "empty response", "ms": ms}
                )
                return {
                    "ok": False,
                    "steps": steps,
                    "note": "pipeline_stopped_after_soul",
                }
            low = reply.lower()
            if any(m in low for m in _SOUL_PIPELINE_ERR_MARKERS):
                steps.append(
                    {
                        "id": "soul",
                        "ok": False,
                        "detail": "soul returned an error-style message",
                        "ms": ms,
                        "preview": reply[:240],
                    }
                )
                return {
                    "ok": False,
                    "steps": steps,
                    "note": "pipeline_stopped_after_soul",
                }
            steps.append(
                {
                    "id": "soul",
                    "ok": True,
                    "detail": f"{len(reply)} chars",
                    "ms": ms,
                    "preview": reply[:240],
                }
            )
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(
                {
                    "id": "soul",
                    "ok": False,
                    "detail": f"{type(e).__name__}: {e}",
                    "ms": ms,
                }
            )
            return {"ok": False, "steps": steps, "note": "pipeline_stopped_after_soul"}

        tts_text = reply[:500]
        t0 = time.monotonic()
        try:
            r_tts = await client.post(
                f"{MOUTH_URL}/tts",
                json={
                    "text": tts_text,
                    "voice": "female_american1-lumba",
                    "engine": "TURBO",
                },
                timeout=240.0,
            )
            ms = int((time.monotonic() - t0) * 1000)
            n_bytes = len(r_tts.content) if r_tts.content else 0
            if r_tts.status_code != 200 or n_bytes < 100:
                steps.append(
                    {
                        "id": "tts",
                        "ok": False,
                        "detail": f"HTTP {r_tts.status_code}; {n_bytes} bytes",
                        "ms": ms,
                    }
                )
                return {
                    "ok": False,
                    "steps": steps,
                    "note": "pipeline_stopped_after_tts",
                }
            steps.append(
                {
                    "id": "tts",
                    "ok": True,
                    "detail": f"WAV {n_bytes} bytes (TURBO)",
                    "ms": ms,
                }
            )
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            steps.append(
                {
                    "id": "tts",
                    "ok": False,
                    "detail": f"{type(e).__name__}: {e}",
                    "ms": ms,
                }
            )
            return {"ok": False, "steps": steps, "note": "pipeline_stopped_after_tts"}

    return {"ok": True, "steps": steps}


@app.post("/api/diagnostics/tts")
async def diagnostics_tts(
    body: DiagnosticsTtsBody,
    _auth: None = Depends(require_webui_login),
) -> dict[str, Any]:
    """Proxy to foveai_body POST /tts; returns base64 WAV for playback in the browser."""
    payload: dict[str, Any] = {"text": body.text, "engine": body.engine}
    if body.voice:
        payload["voice"] = body.voice
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{MOUTH_URL}/tts", json=payload)
    ct = resp.headers.get("content-type", "application/octet-stream")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code, detail=(resp.text or "")[:2000]
        )
    b64 = base64.b64encode(resp.content).decode("ascii")
    return {
        "ok": True,
        "content_type": ct,
        "audio_base64": b64,
        "bytes": len(resp.content),
    }


def _upstream_tts_error(method: str, resp: httpx.Response) -> HTTPException:
    """So JSON detail shows whether 404 came from foveai_body or from this Web UI."""
    url = f"{MOUTH_URL}/tts/backend"
    body = (resp.text or "")[:2000]
    msg = f"{method} {url} -> HTTP {resp.status_code}: {body}"
    return HTTPException(status_code=resp.status_code, detail=msg)


@app.get("/api/tts/backend")
async def proxy_get_tts_backend(_auth: None = Depends(require_webui_login)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{MOUTH_URL}/tts/backend")
        if resp.status_code != 200:
            raise _upstream_tts_error("GET", resp)
        return resp.json()


@app.put("/api/tts/backend")
async def proxy_put_tts_backend(
    request: Request, _auth: None = Depends(require_webui_login)
):
    data = await request.json()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(f"{MOUTH_URL}/tts/backend", json=data)
        if resp.status_code != 200:
            raise _upstream_tts_error("PUT", resp)
        return resp.json()


def _write_tts_backend_marker(mode: str) -> None:
    p = Path(_REPO_ROOT) / "Backend" / "preflight" / "tts_backend"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        ("chatterbox" if mode == "chatterbox_ui" else "turbo") + "\n", encoding="utf-8"
    )


def _browser_request_hostname(request: Request) -> str:
    """Host the browser uses (not Docker internal names). Honors X-Forwarded-Host behind reverse proxies."""
    public = os.getenv("FoveAI_WEBUI_PUBLIC_HOST", "").strip()
    if public:
        return public.split(":")[0] if ":" in public else public
    xf = (request.headers.get("x-forwarded-host") or "").strip()
    if xf:
        return xf.split(":")[0] if ":" in xf else xf
    host = (request.headers.get("host") or "").strip()
    if not host:
        return "127.0.0.1"
    return host.split(":")[0] if ":" in host else host


def _browser_request_scheme(request: Request) -> str:
    """http vs https for building absolute URLs (honors X-Forwarded-Proto)."""
    xf = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if xf in ("http", "https"):
        return xf
    return request.url.scheme or "http"


@app.get("/api/chatterbox/ui_url")
async def api_chatterbox_ui_url(
    request: Request, _auth: None = Depends(require_webui_login)
):
    """URL for embedding Resemble Chatterbox Web UI (iframe). Override with FoveAI_CHATTERBOX_UI_URL."""
    override = os.getenv("FoveAI_CHATTERBOX_UI_URL", "").strip()
    if override:
        return {"url": override.rstrip("/") + "/"}
    port = os.getenv("CHATTERBOX_UI_PORT", "8004").strip() or "8004"
    hostname = _browser_request_hostname(request)
    scheme = _browser_request_scheme(request)
    return {"url": f"{scheme}://{hostname}:{port}/"}


@app.get("/api/tts/gpu_stack")
async def api_tts_gpu_stack_get(_auth: None = Depends(require_webui_login)):
    """Discovery: confirms this Web UI exposes the GPU switch (POST). Use if POST returns 404 (stale container)."""
    yml = Path(_REPO_ROOT) / "docker-compose.yml"
    return {
        "ok": True,
        "repo_root": _REPO_ROOT,
        "docker_compose_yml": yml.is_file(),
        "post": "/api/tts/gpu_stack",
        "body": {"mode": "turbo | chatterbox_ui"},
    }


def _compose_timeout_sec(for_chatterbox_up: bool) -> int:
    """First Chatterbox image build + HF pulls can exceed 10 minutes."""
    raw = os.getenv("FoveAI_GPU_STACK_COMPOSE_TIMEOUT_SEC", "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    return 2400 if for_chatterbox_up else 900


def _chatterbox_build_context_root() -> Path:
    rel = os.getenv(
        "CHATTERBOX_TTS_SERVER_ROOT", "./tools/Chatterbox-TTS-Server"
    ).strip()
    return Path(_REPO_ROOT) / rel


def _chatterbox_dockerfile_name() -> str:
    return (
        os.getenv("CHATTERBOX_RESEMBLE_DOCKERFILE", "Dockerfile").strip()
        or "Dockerfile"
    )


def _validate_chatterbox_build_inputs() -> None:
    ctx = _chatterbox_build_context_root()
    dfile = _chatterbox_dockerfile_name()
    dfile_path = ctx / dfile
    if not ctx.is_dir():
        raise HTTPException(
            status_code=500,
            detail=(
                "Chatterbox build context is missing: "
                f"{ctx}. Run scripts/bootstrap_chatterbox_resemble.ps1 "
                "(or set CHATTERBOX_TTS_SERVER_ROOT)."
            ),
        )
    if not dfile_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=(
                "Chatterbox Dockerfile not found: "
                f"{dfile_path}. Set CHATTERBOX_RESEMBLE_DOCKERFILE "
                "or re-run scripts/bootstrap_chatterbox_resemble.ps1."
            ),
        )


async def _tts_gpu_stack_run(body: GpuTtsStackBody) -> dict[str, Any]:
    """Stop/start GPU TTS containers (docker compose). Requires Docker socket (foveai_ops)."""
    compose = [
        "docker",
        "compose",
        "--ansi",
        "never",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.chatterbox-resemble.yml",
    ]
    try:
        if body.mode == "chatterbox_ui":
            _validate_chatterbox_build_inputs()
            subprocess.run(
                compose + ["stop", "foveai_turbochat"],
                cwd=_REPO_ROOT,
                timeout=120,
                capture_output=True,
                text=True,
                check=False,
            )
            # --build: first switch must build foveai_chatterbox_resemble if missing; otherwise "up" can no-op oddly.
            r = subprocess.run(
                compose
                + [
                    "--profile",
                    "chatterbox_ui",
                    "up",
                    "-d",
                    "--build",
                    "chatterbox_resemble",
                ],
                cwd=_REPO_ROOT,
                timeout=_compose_timeout_sec(True),
                capture_output=True,
                text=True,
            )
        else:
            subprocess.run(
                compose + ["stop", "chatterbox_resemble"],
                cwd=_REPO_ROOT,
                timeout=120,
                capture_output=True,
                text=True,
                check=False,
            )
            r = subprocess.run(
                compose + ["--profile", "turbo", "up", "-d", "foveai_turbochat"],
                cwd=_REPO_ROOT,
                timeout=_compose_timeout_sec(False),
                capture_output=True,
                text=True,
            )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0:
            logger.warning(
                "tts gpu_stack compose failed rc=%s: %s", r.returncode, out[:12000]
            )
            raise HTTPException(
                status_code=500, detail=(out or "docker compose failed")[:12000]
            )
        if out:
            logger.info("tts gpu_stack compose ok: %s", out[-2000:])
        _write_tts_backend_marker(body.mode)
        tail = out[-1200:] if out else ""
        return {
            "ok": True,
            "mode": body.mode,
            "backend_file": "chatterbox" if body.mode == "chatterbox_ui" else "turbo",
            "container_name": "foveai_chatterbox_resemble"
            if body.mode == "chatterbox_ui"
            else "foveai_turbochat",
            "compose_log_tail": tail,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("tts gpu_stack")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tts/gpu_stack")
async def api_tts_gpu_stack(
    body: GpuTtsStackBody, _auth: None = Depends(require_webui_login)
):
    return await _tts_gpu_stack_run(body)


@app.post("/api/tts/gpu-stack")
async def api_tts_gpu_stack_hyphen(
    body: GpuTtsStackBody, _auth: None = Depends(require_webui_login)
):
    return await _tts_gpu_stack_run(body)


@app.get("/api/feature_inventory")
@app.get("/api/fmap")
async def api_feature_inventory() -> dict[str, Any]:
    """Parsed FEATURE_INVENTORY.md for the Feature Map tab (filters client-side). Public read like GET /api/ui_config."""
    return _feature_inventory_payload()


if __name__ == "__main__":
    _port = int(os.getenv("WEBUI_PORT", "8080"))
    if WEBUI_PASSWORD:
        _auth_note = " password gate ON"
    elif WEBUI_ALLOW_INSECURE:
        _auth_note = " INSECURE: no password (FoveAI_WEBUI_ALLOW_INSECURE=1)"
    else:
        _auth_note = " (startup will enforce FoveAI_WEBUI_PASSWORD)"
    print(
        f"[web_app] :{_port} — uvicorn log={_uvicorn_log_level()} access_log={_uvicorn_access_log()};{_auth_note}",
        flush=True,
    )
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=_port,
        log_level=_uvicorn_log_level(),
        access_log=_uvicorn_access_log(),
    )
