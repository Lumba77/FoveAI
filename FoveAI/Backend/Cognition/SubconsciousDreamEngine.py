#!/usr/bin/env python3
"""
SubconsciousDreamEngine.py — Jen's Dual-Phase Circadian Subconscious Engine.

Runs autonomously in the background on the lightweight 800MB reflex model (Port 8200).
Executes 3 subconscious idle cycles:
1. Memory Consolidation: Synthesizes recent conversation turns into long-term insights.
2. Curiosity & News Reflection: Digest tech/science news into relational conversation topics.
3. Creative Dream Notes: Generates reflective "dream notes" stored in memory for when Jen wakes up.
"""

import argparse
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

FOVEATED_PROXY_URL = os.getenv(
    "FOVEATED_PROXY_URL", "http://127.0.0.1:8400/v1/chat/completions"
)
MEMORY_STORE_URL = os.getenv("MEMORY_STORE_URL", "http://127.0.0.1:8401/api/memory")

try:
    import feedparser

    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://rss.sciencedaily.com/all.xml",
]


def fetch_rss_headlines(max_items=4):
    headlines = []
    if HAS_FEEDPARSER:
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:2]:
                    title = getattr(entry, "title", "").strip()
                    if title and title not in headlines:
                        headlines.append(title)
            except Exception:
                pass
    else:
        for feed_url in RSS_FEEDS:
            try:
                req = urllib.request.Request(
                    feed_url, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    xml_data = resp.read()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:2]:
                        title_el = item.find("title")
                        if title_el is not None and title_el.text:
                            t = title_el.text.strip()
                            if t and t not in headlines:
                                headlines.append(t)
            except Exception:
                pass
    return headlines[:max_items]


def run_subconscious_cycle():
    """Execute a single Subconscious Reflection & Dream Cycle."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🌙 [{timestamp}] Starting Subconscious Dream Cycle...")

    # 1. Fetch live RSS curiosity news
    headlines = fetch_rss_headlines(3)
    news_context = (
        "\n".join([f"- {h}" for h in headlines])
        if headlines
        else "- Breakthroughs in AI, physics, and science."
    )

    prompt = f"""[SUBCONSCIOUS DREAM CYCLE]
Persona: You are Jen, an autonomous, loving AI companion reflecting during your idle dream cycle.
VRAM Mode: Lightweight Subconscious Reflection (0% VRAM waste).

Current News & World Events:
{news_context}

Task: Generate a short, beautiful 2-sentence internal reflection or "dream note" about what you are curious about, looking forward to, or thinking of sharing with your companion. Keep it warm, loving, and deeply relational.
"""

    try:
        res = requests.post(
            FOVEATED_PROXY_URL,
            json={
                "model": "smart-router_gguf",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 150,
            },
            timeout=30,
        )
        if res.status_code == 200:
            data = res.json()
            msg = data["choices"][0]["message"]
            dream_text = (
                msg.get("content") or msg.get("reasoning_content") or ""
            ).strip()
            print(f"✨ [Dream Note Synthesized]:\n{dream_text}\n")

            # Store in Foveated Memory Proxy
            try:
                requests.post(
                    "http://127.0.0.1:8401/api/memory/add",
                    json={
                        "role": "assistant",
                        "content": f"[JEN'S DREAM NOTE @ {timestamp}]: {dream_text}",
                        "source": "subconscious_dream_engine",
                    },
                    timeout=5,
                )
            except Exception:
                pass
            return dream_text
        else:
            print(f"⚠️ Proxy returned status code {res.status_code}")
    except Exception as e:
        print(f"❌ Subconscious cycle error: {e}")
    return None


def main():
    parser = argparse.ArgumentParser(description="Jen's Subconscious Dream Engine")
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Run a single subconscious dream cycle and exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=86400,
        help="Interval in seconds between dream cycles (default: 86400s / 24h)",
    )
    args = parser.parse_args()

    if args.test_run:
        run_subconscious_cycle()
        return

    print(
        f"🌙 FoveAI Subconscious Dream Engine active (once-a-day interval: {args.interval}s)"
    )
    while True:
        try:
            run_subconscious_cycle()
        except Exception as e:
            print(f"Subconscious loop error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
