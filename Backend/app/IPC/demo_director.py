"""
demo_director.py — Watch the Director plan events and build a sequence.
Shows the full pipeline: context → plan → suspense → event.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from director_daemon import DirectorDaemon, EventPlan


class MockWebSocket:
    """Mock WebSocket server that just prints what would be broadcast."""

    async def broadcast(self, event, payload):
        if event == "director.suspense.build":
            print("  🎵 [BROADCAST] director.suspense.build")
            print(
                f"     intensity={payload.get('intensity', 0.5)} "
                f"duration={payload.get('duration', 120):.0f}s "
                f"genre={payload.get('genre', 'None')}"
            )
            print("     → The room fills with a low drone. Distant thunder...")
        elif event == "director.suspense.threshold":
            print("  ⚡ [BROADCAST] director.suspense.threshold")
            print("     → Everything goes silent. The held breath.")
            print(f"     → Narrator: '{payload.get('text', '...now.')}'")
        elif event == "director.event":
            print("  🎬 [BROADCAST] director.event")
            print(f"     type={payload.get('eventType')} genre={payload.get('genre')}")
            if payload.get("characterName"):
                print(f"     character={payload['characterName']}")
            if payload.get("narratorLines"):
                for line in payload["narratorLines"][:3]:
                    print(f'     narrator: "{line}"')
            if payload.get("dialogue"):
                for line in payload["dialogue"][:3]:
                    print(f'     dialogue: "{line}"')
        elif event == "director.surprise":
            print("  ✨ [BROADCAST] director.surprise")
            print(f"     surpriseType={payload.get('surpriseType')}")
            print('     → Alice: "oh— look..."')
        elif event == "director.garden.seed":
            print("  🌱 [BROADCAST] director.garden.seed")
            print(f'     concept="{payload.get("concept")}"')
        elif event == "director.garden.beat":
            print("  🎬 [BROADCAST] director.garden.beat")
            print(
                f'     thread="{payload.get("threadTitle")}" beat="{payload.get("beat")}"'
            )
        else:
            print(f"  [BROADCAST] {event}")


def print_header(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


async def main():
    ws = MockWebSocket()
    director = DirectorDaemon(ws_server=ws, min_interval=1, max_interval=2)

    # Patch asyncio.sleep to be instant for demo purposes
    real_sleep = asyncio.sleep

    async def fast_sleep(duration):
        # Print what would be happening during the sleep
        if duration > 5:
            print(
                f"     ... (waiting {duration:.0f}s in real time, instant in demo) ..."
            )
        await real_sleep(0.01)

    asyncio.sleep = fast_sleep

    # ──────────────────────────────────────────────
    print_header("DEMO 1 — The Director Plans an Event")
    print("The Director decides what should happen next...\n")

    plan = director._procedural_plan_event()
    print(f"  Event type: {plan.event_type}")
    print(f"  Genre: {plan.genre}")
    if plan.character_name:
        print(f"  Character: {plan.character_name}")
    print(f"  Duration: {plan.duration:.0f}s")
    print("  Narrator lines:")
    for line in plan.narrator_lines:
        print(f'    "{line}"')
    if plan.dialogue_lines:
        print("  Dialogue:")
        for line in plan.dialogue_lines:
            print(f'    "{line}"')

    # ──────────────────────────────────────────────
    print_header("DEMO 2 — Suspense Building + Event Trigger")
    print("The Director builds suspense before the event...\n")

    # Create a horror plan to show full suspense
    horror_plan = EventPlan(
        event_type="genre_shift",
        payload={"genre": "Horror"},
        genre="Horror",
        narrator_lines=[
            "the lights flicker. something is wrong.",
            "you feel it before you see it.",
        ],
        duration=120,
    )

    print("  Plan: Horror genre shift")
    print("  The Director decides to build suspense first...\n")

    # This will broadcast suspense.build, wait, then broadcast the event
    print("  ── Triggering with suspense ──\n")
    await director._trigger_event(horror_plan)

    # ──────────────────────────────────────────────
    print_header("DEMO 3 — Shared Surprises")
    print("Lighter events — things that happen in the world...\n")

    surprises = [
        "Fireflies",
        "BirdOnWindowsill",
        "MeteorCrossing",
        "CatWandersIn",
        "WhaleSong",
    ]
    for s in surprises:
        await director._trigger_shared_surprise(s)
        print()

    # ──────────────────────────────────────────────
    print_header("DEMO 4 — Story Garden Integration")
    print("The Director plants a seed from conversation...\n")

    director._conversation_summary = (
        "we were talking about feeling lonely at night and hearing strange sounds"
    )
    seed = director.garden.plant_seed_from_conversation(director._conversation_summary)
    if seed:
        print(f'  Planted: "{seed.concept}"')
        print(f"  Source: {seed.source}")
        print(f"  Growth rate: {seed.growth_rate}/day")
        print("  Branches:")
        for b in seed.branches:
            print(f"    → {b}")
    print()

    # ──────────────────────────────────────────────
    print_header("DEMO 5 — Plot History")
    print("The Director remembers what has happened...\n")

    for entry in director.get_plot_history():
        print(f"  [{entry['event_type']}] {entry['summary']}")

    # ──────────────────────────────────────────────
    print_header("DEMO 6 — Riders on the Storm (Sequence)")
    print("The full scripted sequence would play out as:\n")

    sequence = [
        ("Phase 1", "Distant thunder rumbles (30s)", "sub-bass drone at 55Hz"),
        (
            "Phase 2",
            "Lightning flashes (20s)",
            "sharp directional light, thunder follows",
        ),
        ("Phase 3", "Rain pours (15s build)", "800 particles, pink noise hiss"),
        ("Phase 4", "The song starts (10s)", "Am-F-C-G progression, electric piano"),
        (
            "Phase 5",
            "Three slow knocks (10s)",
            "80Hz resonant, 3s apart, getting louder",
        ),
        ("Phase 6", "Silence (5s)", "music stops, rain continues, door opens"),
        ("Phase 7", "THE TWIST", "one of 8 possibilities..."),
    ]

    for phase, desc, detail in sequence:
        print(f"  {phase}: {desc}")
        print(f"    → {detail}")
        print()

    twists = [
        "A soaking wet cat that walks to Alice and purrs",
        "A child with a paper boat who says nothing",
        "An old radio playing the song, voice through static",
        "A second Alice: 'take care of her. she takes care of you.'",
        "A single rose with a note: 'remember.'",
        "A letter: 'I found you.'",
        "A mirror showing you standing in the rain",
        "Nothing — it all stops, but a rose remains",
    ]

    print("  The 8 possible twists:")
    for i, twist in enumerate(twists):
        print(f"    {i}: {twist}")

    print()
    print("  The Director picks one at random each time.")
    print("  You never know which one you'll get.")

    # ──────────────────────────────────────────────
    print_header("DEMO 7 — Director Preferences")
    print("The Director respects user preferences...\n")

    director.set_preferences(
        allow_horror=False, allow_violence=False, allow_surreal=True
    )
    print("  Set: no horror, no violence, surreal allowed")
    print(f"  allow_horror={director.allow_horror}")
    print(f"  allow_violence={director.allow_violence}")
    print(f"  allow_surreal={director.allow_surreal}")
    print()
    print("  The Director will now avoid horror and war genres,")
    print("  but can still do surreal dreams, mysteries, and sci-fi.")


if __name__ == "__main__":
    asyncio.run(main())
