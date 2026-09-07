# FoveAI Google Consent Bridge
# Handles OAuth 2.0 consent, token refresh, and scoped data fetching.
# Only reads what the user explicitly consents to. No write access.

import os
import json
import time
import base64
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    raise ImportError("requests required. Run: pip install requests")

# --- Config via env (no hardcoded secrets) ---
CLIENT_ID = os.getenv("FoveAI_GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("FoveAI_GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("FoveAI_GOOGLE_REDIRECT_URI", "http://127.0.0.1:8765/google/callback")
TOKEN_FILE = os.getenv("FoveAI_GOOGLE_TOKEN_FILE", ".cache/google_tokens.json")

# Scopes we request — user sees each one on consent screen
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",      # Email metadata + body
    "https://www.googleapis.com/auth/calendar.readonly",   # Events
    "https://www.googleapis.com/auth/contacts.readonly",   # People
    "https://www.googleapis.com/auth/userinfo.profile",    # Name, photo
    "https://www.googleapis.com/auth/drive.appdata",       # Appdata folder (invisible to user)
]

DATA_DIR = Path(os.getenv("FoveAI_DATA_DIR", "Data/Consent"))

class GoogleConsentBridge:
    def __init__(self, scopes=None):
        self.scopes = scopes or DEFAULT_SCOPES
        self.tokens = {}
        self.token_path = Path(TOKEN_FILE)
        self._load_tokens()

    def _load_tokens(self):
        if self.token_path.exists():
            try:
                self.tokens = json.loads(self.token_path.read_text())
            except Exception as e:
                print(f"Failed to load tokens: {e}")

    def _save_tokens(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(self.tokens, indent=2))

    def get_auth_url(self) -> str:
        """Generate the Google OAuth consent URL."""
        scope_str = " ".join(self.scopes)
        url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            "&response_type=code"
            f"&scope={scope_str}"
            "&access_type=offline"
            "&prompt=consent"
            "&include_granted_scopes=true"
        )
        return url

    def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        data["obtained_at"] = time.time()
        self.tokens = data
        self._save_tokens()
        return data

    def _refresh_if_needed(self) -> str:
        """Return valid access token, refreshing if expired."""
        if not self.tokens:
            raise RuntimeError("No tokens. User must consent first.")
        expires_at = self.tokens.get("obtained_at", 0) + self.tokens.get("expires_in", 3600)
        if time.time() > expires_at - 60:
            # Refresh
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": self.tokens.get("refresh_token"),
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            resp.raise_for_status()
            new_data = resp.json()
            new_data["obtained_at"] = time.time()
            # Preserve refresh token if not returned
            if "refresh_token" not in new_data and "refresh_token" in self.tokens:
                new_data["refresh_token"] = self.tokens["refresh_token"]
            self.tokens.update(new_data)
            self._save_tokens()
        return self.tokens["access_token"]

    def _get(self, url: str, params=None) -> dict:
        token = self._refresh_if_needed()
        resp = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30
        )
        if resp.status_code == 401:
            # Force refresh and retry once
            self.tokens.pop("obtained_at", None)
            token = self._refresh_if_needed()
            resp = requests.get(
                url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30
            )
        resp.raise_for_status()
        return resp.json()

    # --- Data fetchers (scoped by what user consented to) ---

    def get_profile(self) -> dict:
        """Basic user profile."""
        return self._get("https://www.googleapis.com/oauth2/v2/userinfo")

    def get_contacts(self, max_results: int = 100) -> List[dict]:
        """Google People API contacts."""
        data = self._get(
            "https://people.googleapis.com/v1/people/me/connections",
            params={"personFields": "names,emailAddresses,photos", "pageSize": max_results},
        )
        return data.get("connections", [])

    def get_calendar_events(self, days: int = 30) -> List[dict]:
        """Calendar events from now +/- days."""
        now = datetime.utcnow()
        time_min = (now - timedelta(days=days)).isoformat() + "Z"
        time_max = (now + timedelta(days=days)).isoformat() + "Z"
        data = self._get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params={"timeMin": time_min, "timeMax": time_max, "maxResults": 100, "singleEvents": "true", "orderBy": "startTime"},
        )
        return data.get("items", [])

    def get_recent_emails(self, max_results: int = 50) -> List[dict]:
        """Gmail message list (metadata only — no body content for privacy)."""
        data = self._get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"maxResults": max_results, "labelIds": "INBOX"},
        )
        messages = data.get("messages", [])
        # Fetch minimal headers only
        enriched = []
        for m in messages[:20]:  # cap at 20 to avoid quota
            try:
                meta = self._get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                    params={"format": "metadata", "metadataHeaders": "Subject,From,Date"},
                )
                headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
                enriched.append({
                    "id": m["id"],
                    "threadId": m.get("threadId"),
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                })
            except Exception as e:
                print(f"Email meta fetch failed: {e}")
        return enriched

    def sync_to_memory(self, memory_base_url: str = "http://127.0.0.1:8002"):
        """Push consented data into FoveAI MEMORY service."""
        import requests as req

        payload = {
            "source": "google_consent",
            "timestamp": time.time(),
            "profile": self.get_profile(),
            "contacts": self.get_contacts(max_results=50),
            "events": self.get_calendar_events(days=14),
            "emails": self.get_recent_emails(max_results=20),
        }

        try:
            r = req.post(f"{memory_base_url}/store", json={
                "content": json.dumps(payload, ensure_ascii=False),
                "role": "system",
                "session_id": "google_consent_sync",
                "topics": ["user_profile", "calendar", "contacts", "email_metadata"],
                "importance": 0.9,
            }, timeout=30)
            print(f"Memory sync: {r.status_code}")
        except Exception as e:
            print(f"Memory sync failed: {e}")

        # Save raw backup locally
        backup_dir = DATA_DIR / "google"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (backup_dir / f"sync_{ts}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    # --- Google Drive Backup (appdata folder) ---
    
    def backup_to_drive(self, data: dict, filename: str = "foveai_memory_backup.json") -> dict:
        """Upload a memory snapshot to Google Drive appdata folder.
        This folder is invisible to the user and doesn't clutter their Drive.
        Survives browser data clearing, device loss, and OS reinstall."""
        token = self._refresh_if_needed()
        
        # Check if file already exists (update instead of create new)
        existing = self._find_drive_file(filename)
        
        if existing:
            # Update existing file
            file_id = existing["id"]
            resp = requests.patch(
                f"https://www.googleapis.com/upload/drive/v3/files/{file_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"uploadType": "media"},
                json=data,
                timeout=60,
            )
        else:
            # Create new file in appdata
            import io
            metadata = {"name": filename, "parents": ["appDataFolder"]}
            boundary = "-------314159265358979323846"
            body_parts = []
            body_parts.append(f"--{boundary}\nContent-Type: application/json; charset=UTF-8\n\n{json.dumps(metadata)}")
            body_parts.append(f"--{boundary}\nContent-Type: application/json\n\n{json.dumps(data)}\n--{boundary}--")
            body = "\n".join(body_parts)
            
            resp = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                data=body.encode("utf-8"),
                params={"uploadType": "multipart"},
                timeout=60,
            )
        
        resp.raise_for_status()
        result = resp.json()
        print(f"[Drive Backup] Saved {filename} (id: {result.get('id', '?')})")
        return result
    
    def restore_from_drive(self, filename: str = "foveai_memory_backup.json") -> Optional[dict]:
        """Download the latest memory snapshot from Google Drive appdata."""
        token = self._refresh_if_needed()
        
        existing = self._find_drive_file(filename)
        if not existing:
            print(f"[Drive Restore] No backup found: {filename}")
            return None
        
        file_id = existing["id"]
        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"alt": "media"},
            timeout=60,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"[Drive Restore] Loaded {filename} ({len(resp.content)} bytes)")
            return data
        else:
            print(f"[Drive Restore] Failed: HTTP {resp.status_code}")
            return None
    
    def _find_drive_file(self, filename: str) -> Optional[dict]:
        """Find a file by name in the appdata folder."""
        token = self._refresh_if_needed()
        try:
            resp = requests.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "spaces": "appDataFolder",
                    "q": f"name='{filename}'",
                    "fields": "files(id,name,modifiedTime,size)",
                },
                timeout=30,
            )
            resp.raise_for_status()
            files = resp.json().get("files", [])
            return files[0] if files else None
        except Exception as e:
            print(f"[Drive] File search failed: {e}")
            return None
    
    def get_drive_backup_status(self) -> dict:
        """Check if a Google Drive backup exists and when it was last updated."""
        existing = self._find_drive_file("foveai_memory_backup.json")
        if existing:
            return {
                "available": True,
                "file_id": existing.get("id"),
                "modified": existing.get("modifiedTime"),
                "size": existing.get("size", "?"),
            }
        return {"available": False}


if __name__ == "__main__":
    bridge = GoogleConsentBridge()
    if not bridge.tokens:
        print("No tokens. Visit this URL to consent:")
        print(bridge.get_auth_url())
    else:
        print("Tokens present. Syncing to memory...")
        bridge.sync_to_memory()
