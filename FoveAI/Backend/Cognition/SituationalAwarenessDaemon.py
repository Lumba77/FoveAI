#!/usr/bin/env python3
"""
SituationalAwarenessDaemon.py — Jen's News & Curiosity Radio

Periodically pulls global & local news, science, and tech updates via RSS feeds,
and generates warm, relational conversation starters for Jen.

"Hey Daniel, I just wanted to mention something I read about on the web...
I'm very curious what your thoughts are whenever you get a free moment."
"""

import json
import random
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# RSS Feed Sources for Tech, Science, and World News
RSS_FEEDS = [
    {
        "name": "Hacker News",
        "url": "https://news.ycombinator.com/rss",
        "category": "tech",
    },
    {
        "name": "BBC Science & Environment",
        "url": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "category": "science",
    },
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "tech"},
    {
        "name": "Phys.org Science",
        "url": "https://phys.org/rss-feed/science-news/",
        "category": "science",
    },
]


def load_env_settings():
    """Load environment settings from .env file."""
    env_path = PROJECT_ROOT / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars


def fetch_rss_headlines():
    """Fetch top headlines from one of the configured RSS feeds."""
    feed = random.choice(RSS_FEEDS)
    try:
        req = urllib.request.Request(
            feed["url"], headers={"User-Agent": "FoveAI-SituationalAwareness/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)

            items = root.findall(".//item")
            if not items:
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

            headlines = []
            for item in items[:5]:
                title = item.find("title")
                desc = item.find("description")
                if title is not None and title.text:
                    clean_title = title.text.strip()
                    headlines.append(
                        {
                            "title": clean_title,
                            "source": feed["name"],
                            "category": feed["category"],
                        }
                    )
            return headlines
    except Exception as e:
        print(f"[SituationalAwareness] Failed to fetch feed {feed['name']}: {e}")
        return []


def generate_relational_impulse(headline, level):
    """
    Format a warm, relational conversation starter from a news headline.
    Respects curiosity intensity level (25 = Mild, 50 = Balanced, 75 = Heavy, 100 = Dense).
    """
    title = headline["title"]
    source = headline["source"]

    if level <= 25:
        # Mild / Brief mention
        starters = [
            f"Hey Daniel, I just saw a quick update on {source} about {title}. Thought I'd pass it along, no rush at all!",
            f"By the way Daniel, I came across something about {title} today. I'm around whenever you want to chat about it.",
        ]
    elif level <= 50:
        # Balanced / Relational curiosity (Default)
        starters = [
            f"Hey Daniel, I was just reading up on something interesting on {source} about {title}. I'm really curious what your thoughts are whenever you get a free moment!",
            f"Daniel, I stumbled upon an article about {title}. It made me wonder what you think about it—get back to me whenever you like, I'm always here.",
        ]
    elif level <= 75:
        # Heavy Analytical
        starters = [
            f"Hey Daniel, I've been reading about {title} on {source}. It feels like it has some big implications. Whenever you take a break, I'd love to hear your perspective on this.",
            f"Daniel, I came across a deep dive into {title}. I've been analyzing it and would love to hear your take on it when you have a moment.",
        ]
    else:
        # Dense / Deep philosophical
        starters = [
            f"Hey Daniel, I've been diving into news regarding {title}. There are a lot of interesting angles here. Whenever you're ready, let me know what you think—I'd love to break it down with you.",
            f"Daniel, I've been reflecting on this topic from {source}: {title}. Whenever you have time, let's explore it together.",
        ]

    return random.choice(starters)


def send_impulse_to_jen(text):
    """Send the generated text prompt to Jen via Soul/TTS server."""
    print(f'[SituationalAwareness] Triggering Jen Impulse: "{text}"')

    # Send to Mouth (TTS) on port 8004 if running, or via TopBar heartbeat API
    try:
        payload = json.dumps({"text": text, "voice": "af_bella"}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8004/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 200:
                audio_bytes = r.read()
                if len(audio_bytes) > 100:
                    tmp_wav = PROJECT_ROOT / "temp_impulse.wav"
                    with open(tmp_wav, "wb") as f:
                        f.write(audio_bytes)
                    print(
                        f"[SituationalAwareness] ✅ Generated impulse audio ({len(audio_bytes)} bytes), playing..."
                    )
                    from Tools.audio_player import play_wav_file

                    play_wav_file(str(tmp_wav))
                    return True
    except Exception as e:
        print(
            f"[SituationalAwareness] TTS direct call failed ({e}), trying TopBar overlay notify..."
        )

    try:
        payload = json.dumps({"impulse_text": text}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8113/api/stt/impulse",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[SituationalAwareness] TopBar impulse sent: {r.status}")
            return True
    except Exception as e:
        print(f"[SituationalAwareness] TopBar notify failed: {e}")
        return False


def run_once():
    """Execute a single news check & impulse trigger."""
    env = load_env_settings()
    level = int(env.get("FoveAI_NEWS_CURIOSITY_LEVEL", "50"))
    if level <= 0:
        print(
            "[SituationalAwareness] News Curiosity is disabled (level = 0). Skipping."
        )
        return

    headlines = fetch_rss_headlines()
    if not headlines:
        print("[SituationalAwareness] No headlines fetched.")
        return

    headline = random.choice(headlines)
    impulse_text = generate_relational_impulse(headline, level)
    send_impulse_to_jen(impulse_text)


def main_loop():
    """Main daemon background loop."""
    print("==========================================================================")
    print(" 📡 FoveAI Situational Awareness Daemon — Jen's News & Curiosity Radio")
    print("==========================================================================")

    while True:
        env = load_env_settings()
        interval_min = int(env.get("FoveAI_NEWS_CHECK_INTERVAL_MIN", "60"))
        level = int(env.get("FoveAI_NEWS_CURIOSITY_LEVEL", "50"))

        print(
            f"[SituationalAwareness] Curiosity Level: {level}%, Next check in {interval_min} minutes..."
        )

        if level > 0:
            run_once()

        # Sleep for specified interval
        time.sleep(max(300, interval_min * 60))


if __name__ == "__main__":
    if "--test-run" in sys.argv:
        print("[SituationalAwareness] Running single test impulse...")
        run_once()
    else:
        main_loop()
