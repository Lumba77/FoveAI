"""
demo_garden.py — Watch the Story Garden grow in accelerated time.

Simulates days passing so you can see seeds sprout, grow, branch,
develop into threads, and finally fruit as narrative events.
"""

import asyncio
import os
import sys

# Add the IPC directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from director_daemon import StoryGarden


def print_header(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_garden(garden):
    status = garden.get_garden_status()
    print(f"  🌱 Total seeds: {status['total_seeds']}")
    print(f"  🌿 Stages: {status['stages']}")
    print(f"  📖 Active threads: {status['active_threads']}")
    print(f"  🍎 Ready to fruit: {status['ready_to_fruit']}")
    print(f"  ⏰ Oldest seed: {status['oldest_seed_days']:.1f} days")
    print()


def print_seeds(garden, filter_status=None):
    for seed in garden.seeds.values():
        if filter_status and seed.status != filter_status:
            continue
        stage_icon = {
            "seed": "🌱",
            "sprout": "🌿",
            "sapling": "🌳",
            "tree": "🌲",
            "fruited": "🍎",
            "withered": "枯",
        }.get(seed.stage, "?")
        print(
            f"  {stage_icon} [{seed.stage:>8}] growth={seed.growth:.2f} "
            f"watered={seed.watered} | {seed.concept}"
        )
        if seed.branches:
            print(f"           branches: {seed.branches[0]}")
            if len(seed.branches) > 1:
                print(f"                    {seed.branches[1]}")
    print()


def print_threads(garden):
    for thread in garden.threads.values():
        status = (
            "🍎 fruited"
            if thread.fruited
            else ("✅ ready" if thread.ready_to_fruit else "📖 growing")
        )
        print(f"  📖 [{status:>12}] '{thread.title}'")
        print(f"     Synopsis: {thread.synopsis}")
        print(
            f"     Beats: {thread.current_beat}/{len(thread.beats)} | "
            f"Tension: {thread.tension:.1f} | Genre: {thread.genre}"
        )
        if thread.characters:
            print(f"     Characters: {', '.join(thread.characters)}")
        print()


async def main():
    garden_path = "C:/Users/danie/program/LUMAX/FoveAI/data/demo_garden.json"

    # Clean start
    if os.path.exists(garden_path):
        os.remove(garden_path)

    garden = StoryGarden(persist_path=garden_path)

    print_header("ACT I — Planting Seeds")
    print("The Director observes the conversation and plants seeds...\n")

    # Plant seeds from conversation observations
    conversations = [
        "we were talking about feeling lonely at night",
        "alice mentioned a dream she had about a door",
        "the user talked about missing someone from their past",
        "alice noticed a strange sound outside",
        "they discussed what it means to be alive",
        "the user said they're afraid of forgetting",
    ]

    for conv in conversations:
        seed = garden.plant_seed_from_conversation(conv)
        if seed:
            print(f"  🌱 Planted: '{seed.concept}'")
            print(f"     Source: {seed.source}")
            print(f"     Growth rate: {seed.growth_rate}/day")
            print()

    # Also plant a couple directly from templates
    garden.plant_seed(source="spontaneous")
    garden.plant_seed(source="spontaneous")

    print(f"\n  Garden now has {len(garden.seeds)} seeds")
    print_garden(garden)

    # ──────────────────────────────────────────────────────────

    print_header("ACT II — Time Passes (Day 3)")
    print("Simulating 3 days of growth...\n")

    # Simulate time passing by adjusting planted_at
    three_days = 3 * 86400
    for seed in garden.seeds.values():
        seed.planted_at -= three_days

    garden.grow()
    print_seeds(garden)
    print_garden(garden)

    # ──────────────────────────────────────────────────────────

    print_header("ACT III — The Director Waters Seeds")
    print("The Director notices interesting seeds and nurtures them...\n")

    # Water the most interesting seeds
    interesting = list(garden.seeds.values())[:3]
    for seed in interesting:
        garden.water(seed.id)
        print(f"  💧 Watered: '{seed.concept}' (now watered {seed.watered}x)")
    print()

    # ──────────────────────────────────────────────────────────

    print_header("ACT IV — More Time Passes (Day 7)")
    print("A week has passed. Seeds are growing...\n")

    seven_days = 7 * 86400
    for seed in garden.seeds.values():
        seed.planted_at -= seven_days - three_days  # additional 4 days

    garden.grow()
    print_seeds(garden)
    print_garden(garden)

    # ──────────────────────────────────────────────────────────

    print_header("ACT V — Cross-Pollination")
    print("Two growing seeds combine into something new...\n")

    new_seed = garden.cross_pollinate()
    if new_seed:
        print(f"  🌺 Cross-pollinated: '{new_seed.concept}'")
        print(f"     Growth rate: {new_seed.growth_rate}/day (slower but richer)")
    print()

    # ──────────────────────────────────────────────────────────

    print_header("ACT VI — Thread Development (Day 14)")
    print("Two weeks now. Mature seeds develop into story threads...\n")

    fourteen_days = 14 * 86400
    for seed in garden.seeds.values():
        if seed.status != "fruited":
            seed.planted_at -= fourteen_days - seven_days  # additional 7 days

    garden.grow()

    mature = garden.get_mature_seeds()
    print(f"  {len(mature)} mature seeds ready to develop:\n")
    print_seeds(garden, filter_status="mature")

    # Develop threads from mature seeds
    for seed in mature[:2]:
        thread = garden.develop_thread(seed.id)
        if thread:
            print(f"  📖 Thread developed: '{thread.title}'")
            print(f"     {len(thread.beats)} narrative beats:")
            for i, beat in enumerate(thread.beats):
                print(f"       Beat {i + 1}: [{beat['beat']}] {beat['description']}")
            print()

    print_garden(garden)
    print_threads(garden)

    # ──────────────────────────────────────────────────────────

    print_header("ACT VII — Beats Advance")
    print("Over the next few days, the thread's beats advance quietly...")
    print("Each beat is a subtle moment — a foreshadowing the user barely notices.\n")

    for thread in garden.threads.values():
        if thread.fruited or thread.ready_to_fruit:
            continue
        # Advance a few beats
        for _ in range(3):
            beat = garden.advance_thread(thread.id)
            if beat is None:
                break
            print(f"  🎬 [{thread.title}] Beat: {beat['beat']}")
            print(f"     {beat['description']}")
            print(f"     Tension: {beat['tension']:.1f}")
            print()

    print_threads(garden)

    # ──────────────────────────────────────────────────────────

    print_header("ACT VIII — The Fruit")
    print("The story is ready. The Director prepares to trigger the event...\n")

    ready = garden.get_ready_threads()
    if ready:
        thread = ready[0]
        print(f"  🍎 Fruiting: '{thread.title}'")
        print(f"     Genre: {thread.genre}")
        print(f"     Characters: {', '.join(thread.characters)}")
        print(f"     Event type: {thread.fruit_event_type}")
        print(f"     Final beat: {thread.beats[-1]['description']}")
        print()
        print("  The Director would now:")
        print("    1. Build suspense (1-5 min audio-only foreshadowing)")
        print("    2. Trigger the event via WebSocket")
        print("    3. The Unity DirectorEngine executes the full scene")
        print("    4. New seeds are planted from this story's fruit")
        print()

        # Fruit it
        fruited = garden.fruit_thread(thread.id)
        print("  ✅ Thread fruited. New seeds may follow...")

    print()
    print_garden(garden)

    # ──────────────────────────────────────────────────────────

    print_header("EPILOGUE — The Garden State")
    print("The garden persists. Seeds continue growing. New stories brew.\n")

    status = garden.get_garden_status()
    print(f"  Seeds total:     {status['total_seeds']}")
    print(f"  Stages:          {status['stages']}")
    print(f"  Active threads:  {status['active_threads']}")
    print(f"  Ready to fruit:  {status['ready_to_fruit']}")
    print(f"  Oldest seed:     {status['oldest_seed_days']:.1f} days")
    print()
    print("  The garden is saved to disk. It will continue growing")
    print("  across sessions. Stories planted today may fruit weeks")
    print("  from now. The Director never forgets.\n")

    # Show all remaining seeds
    print("  Living seeds in the garden:")
    print_seeds(garden)

    # Cleanup
    if os.path.exists(garden_path):
        os.remove(garden_path)
        print("  (Demo garden cleaned up. Real garden at data/story_garden.json)")


if __name__ == "__main__":
    asyncio.run(main())
