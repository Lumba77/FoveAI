# FoveAI Microsoft Consent Bridge
# Handles Microsoft Graph OAuth 2.0 consent, token refresh, and scoped data fetching.

import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    raise ImportError("requests required. Run: pip install requests")

CLIENT_ID = os.getenv("FoveAI_MS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("FoveAI_MS_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("FoveAI_MS_REDIRECT_URI", "http://127.0.0.1:8765/microsoft/callback")
TOKEN_FILE = os.getenv("FoveAI_MS_TOKEN_FILE", ".cache/ms_tokens.json")

DEFAULT_SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Contacts.Read",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Mail.ReadBasic",
]

DATA_DIR = Path(os.getenv("FoveAI_DATA_DIR", "Data/Consent"))

class MicrosoftConsentBridge:
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
                print(f"Failed to load MS tokens: {e}")

    def _save_tokens(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(self.tokens, indent=2))

    def get_auth_url(self) -> str:
        scope_str = " ".join(self.scopes)
        url = (
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            "&response_type=code"
            f"&scope={scope_str}"
            "&prompt=consent"
        )
        return url

    def exchange_code(self, code: str) -> dict:
        resp = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
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
        if not self.tokens:
            raise RuntimeError("No MS tokens. User must consent first.")
        expires_at = self.tokens.get("obtained_at", 0) + self.tokens.get("expires_in", 3600)
        if time.time() > expires_at - 60:
            resp = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": self.tokens.get("refresh_token"),
                    "grant_type": "refresh_token",
                    "scope": " ".join(self.scopes),
                },
                timeout=30,
            )
            resp.raise_for_status()
            new_data = resp.json()
            new_data["obtained_at"] = time.time()
            if "refresh_token" not in new_data and "refresh_token" in self.tokens:
                new_data["refresh_token"] = self.tokens["refresh_token"]
            self.tokens.update(new_data)
            self._save_tokens()
        return self.tokens["access_token"]

    def _get(self, endpoint: str, params=None) -> dict:
        token = self._refresh_if_needed()
        url = f"https://graph.microsoft.com/v1.0{endpoint}"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
        if resp.status_code == 401:
            self.tokens.pop("obtained_at", None)
            token = self._refresh_if_needed()
            resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_profile(self) -> dict:
        return self._get("/me")

    def get_contacts(self, max_results: int = 50) -> List[dict]:
        data = self._get("/me/contacts", params={"$top": max_results, "$select": "displayName,emailAddresses"})
        return data.get("value", [])

    def get_calendar_events(self, days: int = 30) -> List[dict]:
        now = datetime.utcnow()
        start = (now - timedelta(days=days)).isoformat() + "Z"
        end = (now + timedelta(days=days)).isoformat() + "Z"
        data = self._get(
            "/me/calendarview",
            params={"startDateTime": start, "endDateTime": end, "$top": 100, "$select": "subject,start,end,location,importance"},
        )
        return data.get("value", [])

    def get_recent_emails(self, max_results: int = 50) -> List[dict]:
        data = self._get("/me/messages", params={"$top": max_results, "$select": "subject,from,toRecipients,receivedDateTime,importance"})
        return data.get("value", [])

    def sync_to_memory(self, memory_base_url: str = "http://127.0.0.1:8002"):
        import requests as req
        payload = {
            "source": "microsoft_consent",
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
                "session_id": "microsoft_consent_sync",
                "topics": ["user_profile", "calendar", "contacts", "email_metadata"],
                "importance": 0.9,
            }, timeout=30)
            print(f"MS Memory sync: {r.status_code}")
        except Exception as e:
            print(f"MS Memory sync failed: {e}")

        backup_dir = DATA_DIR / "microsoft"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (backup_dir / f"sync_{ts}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    bridge = MicrosoftConsentBridge()
    if not bridge.tokens:
        print("No MS tokens. Visit this URL to consent:")
        print(bridge.get_auth_url())
    else:
        print("MS Tokens present. Syncing to memory...")
        bridge.sync_to_memory()