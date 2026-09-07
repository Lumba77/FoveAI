"""
director_daemon.py — The Off-Scene AI Director
================================================

A creative AI that orchestrates surprise narrative events in the VR experience.

The Director:
  • Reads summarized plots of user↔Alice interactions
  • Plans interesting events and scenes in advance
  • Builds whole scenarios (horror, war, mystery, comedy, romance)
  • Triggers them at surprising moments via WebSocket
  • Develops scenes over time — they grow, escalate, resolve

Architecture:
  • Runs as a background async daemon
  • Polls conversation memory for context
  • Uses an LLM to generate creative event plans
  • Maintains a "plot timeline" of upcoming events
  • Sends director.* events to the WebSocket server
  • Respects user preferences (no horror if disabled, etc.)

Usage:
    from Backend.app.IPC.director_daemon import DirectorDaemon
    director = DirectorDaemon(ws_server=ipc_server)
    await director.start()
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("FoveAI.Director")

# ── Event Plan ──────────────────────────────────────────────────────────────

@dataclass
class EventPlan:
    """A planned event the Director has prepared."""
    event_type: str               # phone_ring, genre_shift, character_arrival, etc.
    payload: dict                 # event-specific data
    genre: str = "None"           # associated genre if any
    character_name: str = ""      # character name if applicable
    dialogue_lines: list = field(default_factory=list)  # scripted dialogue
    narrator_lines: list = field(default_factory=list)  # narration
    build_time: float = 5.0       # atmosphere build before event
    duration: float = 180.0       # estimated duration
    priority: int = 0             # higher = more important
    created_at: float = field(default_factory=time.time)
    triggered: bool = False
    tags: list = field(default_factory=list)


# ── Story Garden ────────────────────────────────────────────────────────────
#
# The Director doesn't just trigger events — it GROWS them.
# Like a garden:
#   • Seeds    — tiny ideas, fragments, "what if" moments
#   • Sprouts  — seeds that have taken root, developing structure
#   • Saplings — growing stories with branches and potential
#   • Trees    — fully developed narrative arcs, ready to bear fruit
#   • Fruits   — the payoff event, the scene that finally happens
#
# A seed planted on Monday might grow into a tree by Thursday and
# bear fruit on Saturday. The user experiences a slow-cooked narrative
# that the Director has been nurturing for days.
#
# Story threads can:
#   • Branch     — a seed splits into multiple possible directions
#   • Cross      — two threads merge into a combined event
#   • Wither     — threads that don't get nurtured die naturally
#   • Graft      — the Director combines elements from multiple threads
#   • Seed again — a fruit drops new seeds for future stories

@dataclass
class StorySeed:
    """A seed — the smallest unit of narrative potential."""
    id: str
    concept: str                  # "a mysterious caller", "a recurring dream"
    source: str = ""              # what inspired this seed (conversation, observation, random)
    planted_at: float = field(default_factory=time.time)
    growth: float = 0.0           # 0.0 = seed, 1.0 = ready to fruit
    growth_rate: float = 0.1      # how fast this seed grows per day
    watered: int = 0              # times the Director has nurtured this seed
    branches: list = field(default_factory=list)  # possible directions
    tags: list = field(default_factory=list)
    status: str = "planted"       # planted, growing, mature, fruited, withered
    parent_seed_id: str = ""      # if this seed came from another seed's fruit
    related_seeds: list = field(default_factory=list)  # IDs of connected seeds

    @property
    def age_days(self) -> float:
        return (time.time() - self.planted_at) / 86400.0

    @property
    def stage(self) -> str:
        if self.status == "withered": return "withered"
        if self.status == "fruited": return "fruited"
        if self.growth < 0.2: return "seed"
        if self.growth < 0.5: return "sprout"
        if self.growth < 0.8: return "sapling"
        return "tree"


@dataclass
class StoryThread:
    """A growing narrative thread — a seed that has developed structure."""
    id: str
    seed_id: str                   # the seed this grew from
    title: str                     # "The Recurring Caller", "Alice's Double"
    synopsis: str                  # brief description of the story arc
    beats: list = field(default_factory=list)  # narrative beats in order
    current_beat: int = 0          # which beat we're on
    characters: list = field(default_factory=list)  # characters involved
    genre: str = "None"
    tension: float = 0.0           # 0-1, builds over time
    planted_at: float = field(default_factory=time.time)
    last_nurtured: float = field(default_factory=time.time)
    ready_to_fruit: bool = False
    fruited: bool = False
    fruit_event_type: str = ""     # what event to trigger when fruiting
    fruit_payload: dict = field(default_factory=dict)

    @property
    def age_days(self) -> float:
        return (time.time() - self.planted_at) / 86400.0


# ── Seed Templates ──────────────────────────────────────────────────────────
# The Director's palette of narrative seeds it can plant.

SEED_TEMPLATES = [
    # Mystery seeds
    {"concept": "a recurring phone call from an unknown number", "genre": "NoirMystery",
     "growth_rate": 0.15, "branches": ["the caller is from the past", "the caller is from the future", "the caller is Alice herself"],
     "fruit_event": "phone_ring"},
    {"concept": "a letter that keeps appearing, always one word more", "genre": "NoirMystery",
     "growth_rate": 0.08, "branches": ["the letter is a warning", "the letter is a love letter", "the letter is a confession"],
     "fruit_event": "prop_spawn"},
    {"concept": "a sound that only Alice can hear", "genre": "SurrealDream",
     "growth_rate": 0.12, "branches": ["it's a frequency from another dimension", "it's her own voice echoing back", "it's the room itself singing"],
     "fruit_event": "narration"},
    # Character seeds
    {"concept": "someone who looks exactly like Alice", "genre": "SurrealDream",
     "growth_rate": 0.06, "branches": ["she's from a parallel timeline", "she's Alice's shadow self", "she's what Alice could become"],
     "fruit_event": "character_arrival"},
    {"concept": "a child who keeps visiting but never speaks", "genre": "None",
     "growth_rate": 0.10, "branches": ["the child is a memory", "the child is lost", "the child is looking for something"],
     "fruit_event": "character_arrival"},
    {"concept": "an old friend Alice never mentioned before", "genre": "None",
     "growth_rate": 0.12, "branches": ["they had a falling out", "they shared a secret", "they owe Alice something"],
     "fruit_event": "character_arrival"},
    # Atmosphere seeds
    {"concept": "the room seems to breathe at night", "genre": "Horror",
     "growth_rate": 0.05, "branches": ["the room is alive", "it's a dream bleeding into reality", "it's the Director's presence"],
     "fruit_event": "genre_shift"},
    {"concept": "a storm that never quite arrives", "genre": "NoirMystery",
     "growth_rate": 0.08, "branches": ["the storm brings something", "the storm is a metaphor", "the storm is real and it's coming"],
     "fruit_event": "event_sequence"},
    # Emotional seeds
    {"concept": "Alice starts remembering things that never happened", "genre": "SurrealDream",
     "growth_rate": 0.07, "branches": ["they're from another life", "they're predictions", "they're the Director's suggestions"],
     "fruit_event": "narration"},
    {"concept": "a recurring dream about a door that won't open", "genre": "SurrealDream",
     "growth_rate": 0.06, "branches": ["the door leads somewhere real", "the door is a memory", "the door is a choice"],
     "fruit_event": "event_sequence"},
    {"concept": "something is watching from outside the window", "genre": "Horror",
     "growth_rate": 0.04, "branches": ["it's curious", "it's lost", "it's hungry"],
     "fruit_event": "genre_shift"},
    # Whimsical seeds
    {"concept": "a cat that appears during every storm", "genre": "None",
     "growth_rate": 0.15, "branches": ["the cat is a guardian", "the cat is looking for its owner", "the cat is not a cat"],
     "fruit_event": "character_arrival"},
    {"concept": "music that plays from no visible source", "genre": "None",
     "growth_rate": 0.12, "branches": ["it's a memory", "it's a signal", "it's the room's heartbeat"],
     "fruit_event": "narration"},
    # Cosmic seeds (slow growing, big payoff)
    {"concept": "the stars are moving into a pattern", "genre": "SciFi",
     "growth_rate": 0.03, "branches": ["it's a message", "it's a countdown", "it's a map"],
     "fruit_event": "genre_shift"},
    {"concept": "a signal from deep space, repeating", "genre": "SciFi",
     "growth_rate": 0.04, "branches": ["it's a greeting", "it's a warning", "it's an echo of ourselves"],
     "fruit_event": "event_sequence"},
    # Relationship seeds
    {"concept": "Alice says something she immediately forgets saying", "genre": "SurrealDream",
     "growth_rate": 0.09, "branches": ["it was a slip from another timeline", "it was the Director speaking through her", "it was a repressed truth"],
     "fruit_event": "narration"},
    {"concept": "a shared memory that you and Alice disagree about", "genre": "None",
     "growth_rate": 0.10, "branches": ["one of you is wrong", "both of you are right in different timelines", "the memory was planted"],
     "fruit_event": "narration"},
]


class StoryGarden:
    """
    The Director's narrative garden.

    Seeds are planted from conversation observations, random inspiration,
    or as fruits of previous stories. They grow over days, developing
    branches and structure. When mature, they bear fruit as events.

    The garden is persistent — it survives across sessions. Stories
    planted today may fruit weeks from now.
    """

    def __init__(self, persist_path: str = ""):
        self.seeds: dict[str, StorySeed] = {}
        self.threads: dict[str, StoryThread] = {}
        self.persist_path = persist_path
        self._seed_counter = 0

        # Load persisted garden
        if persist_path:
            self._load()

    def plant_seed(self, concept: str = "", source: str = "", template: dict | None = None) -> StorySeed:
        """Plant a new narrative seed."""
        if template is None:
            # Pick a random template if no concept given
            template = random.choice(SEED_TEMPLATES)
            if concept:
                template = {**template, "concept": concept}

        seed_id = f"seed_{int(time.time())}_{self._seed_counter}"
        self._seed_counter += 1

        seed = StorySeed(
            id=seed_id,
            concept=template.get("concept", concept or "an unformed idea"),
            source=source or template.get("source", "spontaneous"),
            growth_rate=template.get("growth_rate", 0.1),
            branches=template.get("branches", []).copy(),
            tags=[template.get("genre", "None")],
        )

        self.seeds[seed_id] = seed
        logger.info(f"[Garden] Planted seed: '{seed.concept}' (growth_rate={seed.growth_rate}/day)")
        self._save()
        return seed

    def plant_seed_from_conversation(self, conversation_summary: str) -> Optional[StorySeed]:
        """Plant a seed inspired by the current conversation."""
        # Simple heuristic — look for emotionally charged topics
        triggers = {
            "lonely": "a presence that visits when you're alone",
            "memory": "a memory that keeps returning",
            "dream": "a dream that bleeds into waking",
            "lost": "something lost that wants to be found",
            "afraid": "a fear that takes shape",
            "love": "a love letter from an unknown sender",
            "death": "a visitor from the other side",
            "future": "a message from your future self",
            "past": "someone from the past who never left",
            "music": "a song that plays from nowhere",
        }

        summary_lower = conversation_summary.lower()
        for trigger, concept in triggers.items():
            if trigger in summary_lower:
                return self.plant_seed(concept=concept, source=f"conversation:{trigger}")

        # Random seed if no trigger matched
        if random.random() < 0.1:  # 10% chance per conversation check
            return self.plant_seed(source="spontaneous")
        return None

    def grow(self) -> None:
        """Grow all seeds by their daily growth rate. Called periodically."""
        now = time.time()
        for seed in list(self.seeds.values()):
            if seed.status in ("withered", "fruited"):
                continue

            # Grow based on time since planted
            days_elapsed = (now - seed.planted_at) / 86400.0
            expected_growth = days_elapsed * seed.growth_rate

            # Watering boosts growth
            growth_with_water = expected_growth + seed.watered * 0.05

            seed.growth = min(1.0, growth_with_water)

            # Update status
            if seed.growth >= 0.8 and seed.status != "mature":
                seed.status = "mature"
                logger.info(f"[Garden] Seed matured: '{seed.concept}' (growth={seed.growth:.2f})")
            elif seed.growth >= 0.2 and seed.status == "planted":
                seed.status = "growing"
                logger.info(f"[Garden] Seed sprouting: '{seed.concept}' (growth={seed.growth:.2f})")

            # Wither seeds that haven't grown in a long time and weren't watered
            if seed.age_days > 30 and seed.watered == 0 and seed.growth < 0.3:
                seed.status = "withered"
                logger.info(f"[Garden] Seed withered: '{seed.concept}' (unwatered for {seed.age_days:.0f} days)")

        self._save()

    def water(self, seed_id: str) -> None:
        """Nurture a seed — the Director pays attention to it, developing it."""
        if seed_id in self.seeds:
            self.seeds[seed_id].watered += 1
            self.seeds[seed_id].growth = min(1.0, self.seeds[seed_id].growth + 0.05)
            logger.info(f"[Garden] Watered seed: '{self.seeds[seed_id].concept}' (watered={self.seeds[seed_id].watered})")
            self._save()

    def develop_thread(self, seed_id: str) -> Optional[StoryThread]:
        """Develop a mature seed into a story thread with structure."""
        seed = self.seeds.get(seed_id)
        if seed is None or seed.growth < 0.5:
            return None

        thread_id = f"thread_{seed_id}"
        if thread_id in self.threads:
            return self.threads[thread_id]

        # Pick a branch
        branch = random.choice(seed.branches) if seed.branches else "the story unfolds naturally"

        # Generate narrative beats
        beats = self._generate_beats(seed.concept, branch, seed.tags)

        thread = StoryThread(
            id=thread_id,
            seed_id=seed_id,
            title=self._generate_title(seed.concept, branch),
            synopsis=f"{seed.concept} — {branch}",
            beats=beats,
            characters=self._extract_characters(seed.concept, branch),
            genre=seed.tags[0] if seed.tags else "None",
            tension=0.0,
            fruit_event_type=self._get_fruit_event(seed),
        )

        self.threads[thread_id] = thread
        logger.info(f"[Garden] Thread developed: '{thread.title}' ({len(beats)} beats, genre={thread.genre})")
        self._save()
        return thread

    def _generate_beats(self, concept: str, branch: str, tags: list) -> list:
        """Generate narrative beats for a story thread."""
        genre = tags[0] if tags else "None"

        beats = [
            {"beat": "the seed", "description": f"{concept} — first hint, barely noticeable", "tension": 0.1},
            {"beat": "the sprout", "description": f"it happens again, you can't ignore it now", "tension": 0.2},
            {"beat": "the turn", "description": f"the direction becomes clear: {branch}", "tension": 0.4},
            {"beat": "the complication", "description": "things are not as simple as they seemed", "tension": 0.6},
            {"beat": "the climax", "description": "the moment of revelation or confrontation", "tension": 0.9},
            {"beat": "the resolution", "description": "the story finds its ending, or its new beginning", "tension": 0.3},
        ]

        # Genre-specific beat modifications
        if genre == "Horror":
            beats.insert(2, {"beat": "the false safety", "description": "you think it's over. it's not.", "tension": 0.15})
        elif genre == "RomanticComedy":
            beats.insert(3, {"beat": "the misunderstanding", "description": "a miscommunication threatens everything", "tension": 0.5})
        elif genre == "SciFi":
            beats.insert(1, {"beat": "the anomaly", "description": "something that shouldn't be possible", "tension": 0.15})

        return beats

    def _generate_title(self, concept: str, branch: str) -> str:
        """Generate a title for a story thread."""
        words = concept.split()
        key_word = words[0] if words else "the"
        return f"{key_word.title()} — {branch.split()[0] if branch else 'untold'}"

    def _extract_characters(self, concept: str, branch: str) -> list:
        """Extract character names from concept and branch."""
        characters = ["Alice"]
        if "caller" in concept.lower() or "phone" in concept.lower():
            characters.append("The Caller")
        if "child" in concept.lower():
            characters.append("The Child")
        if "friend" in concept.lower():
            characters.append("The Old Friend")
        if "cat" in concept.lower():
            characters.append("The Cat")
        if "double" in concept.lower() or "like alice" in concept.lower():
            characters.append("The Other Alice")
        return characters

    def _get_fruit_event(self, seed: StorySeed) -> str:
        """Determine what event type a seed fruits into."""
        for template in SEED_TEMPLATES:
            if template.get("concept") == seed.concept:
                return template.get("fruit_event", "narration")
        return "narration"

    def get_mature_seeds(self) -> list[StorySeed]:
        """Get all seeds that are mature and ready to fruit."""
        return [s for s in self.seeds.values() if s.status == "mature"]

    def get_growing_seeds(self) -> list[StorySeed]:
        """Get all seeds that are actively growing."""
        return [s for s in self.seeds.values() if s.status in ("growing", "mature")]

    def get_ready_threads(self) -> list[StoryThread]:
        """Get threads that are ready to bear fruit."""
        return [t for t in self.threads.values() if t.ready_to_fruit and not t.fruited]

    def fruit_seed(self, seed_id: str) -> Optional[StorySeed]:
        """Mark a seed as fruited and return it for event triggering."""
        seed = self.seeds.get(seed_id)
        if seed is None:
            return None
        seed.status = "fruited"
        logger.info(f"[Garden] Seed fruited: '{seed.concept}'")
        self._save()
        return seed

    def fruit_thread(self, thread_id: str) -> Optional[StoryThread]:
        """Mark a thread as fruited and return it."""
        thread = self.threads.get(thread_id)
        if thread is None:
            return None
        thread.fruited = True
        # Mark the parent seed as fruited too
        if thread.seed_id in self.seeds:
            self.seeds[thread.seed_id].status = "fruited"
        # Plant new seeds from the fruit
        self._plant_seeds_from_fruit(thread)
        logger.info(f"[Garden] Thread fruited: '{thread.title}'")
        self._save()
        return thread

    def _plant_seeds_from_fruit(self, thread: StoryThread) -> None:
        """When a story fruits, it drops new seeds for future stories."""
        # 30% chance to plant a follow-up seed
        if random.random() < 0.3:
            follow_ups = [
                f"the aftermath of {thread.title.lower()}",
                f"someone remembers what happened with {thread.title.lower()}",
                f"the consequences of {thread.synopsis.lower()}",
            ]
            concept = random.choice(follow_ups)
            self.plant_seed(concept=concept, source=f"fruit:{thread.id}")

    def advance_thread(self, thread_id: str) -> Optional[dict]:
        """Advance a thread to its next beat. Returns the beat, or None if complete."""
        thread = self.threads.get(thread_id)
        if thread is None or thread.fruited:
            return None

        if thread.current_beat >= len(thread.beats):
            thread.ready_to_fruit = True
            return None

        beat = thread.beats[thread.current_beat]
        thread.current_beat += 1
        thread.tension = beat.get("tension", 0.5)
        thread.last_nurtured = time.time()

        # If this was the last beat, mark as ready to fruit
        if thread.current_beat >= len(thread.beats):
            thread.ready_to_fruit = True
            logger.info(f"[Garden] Thread ready to fruit: '{thread.title}'")

        self._save()
        return beat

    def cross_pollinate(self) -> Optional[StorySeed]:
        """Sometimes two growing seeds combine into something new."""
        growing = self.get_growing_seeds()
        if len(growing) < 2:
            return None

        # Pick two random growing seeds
        s1, s2 = random.sample(growing, 2)

        # Combine their concepts
        combined_concept = f"{s1.concept} intertwined with {s2.concept}"
        combined_branches = s1.branches + s2.branches

        seed = self.plant_seed(
            concept=combined_concept,
            source=f"cross:{s1.id}+{s2.id}",
        )
        seed.branches = combined_branches
        seed.related_seeds = [s1.id, s2.id]
        seed.growth_rate = max(s1.growth_rate, s2.growth_rate) * 0.8  # slower but richer

        logger.info(f"[Garden] Cross-pollinated: '{s1.concept}' × '{s2.concept}'")
        return seed

    def get_garden_status(self) -> dict:
        """Get a summary of the garden's state."""
        stages = {"seed": 0, "sprout": 0, "sapling": 0, "tree": 0, "fruited": 0, "withered": 0}
        for seed in self.seeds.values():
            stages[seed.stage] = stages.get(seed.stage, 0) + 1

        return {
            "total_seeds": len(self.seeds),
            "stages": stages,
            "active_threads": len([t for t in self.threads.values() if not t.fruited]),
            "ready_to_fruit": len(self.get_mature_seeds()) + len(self.get_ready_threads()),
            "oldest_seed_days": max((s.age_days for s in self.seeds.values()), default=0),
        }

    def _save(self) -> None:
        """Persist the garden to disk."""
        if not self.persist_path:
            return
        try:
            import json
            data = {
                "seeds": {sid: {
                    "id": s.id, "concept": s.concept, "source": s.source,
                    "planted_at": s.planted_at, "growth": s.growth,
                    "growth_rate": s.growth_rate, "watered": s.watered,
                    "branches": s.branches, "tags": s.tags,
                    "status": s.status, "parent_seed_id": s.parent_seed_id,
                    "related_seeds": s.related_seeds,
                } for sid, s in self.seeds.items()},
                "threads": {tid: {
                    "id": t.id, "seed_id": t.seed_id, "title": t.title,
                    "synopsis": t.synopsis, "beats": t.beats,
                    "current_beat": t.current_beat, "characters": t.characters,
                    "genre": t.genre, "tension": t.tension,
                    "planted_at": t.planted_at, "last_nurtured": t.last_nurtured,
                    "ready_to_fruit": t.ready_to_fruit, "fruited": t.fruited,
                    "fruit_event_type": t.fruit_event_type,
                } for tid, t in self.threads.items()},
            }
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[Garden] Save failed: {e}")

    def _load(self) -> None:
        """Load the garden from disk."""
        if not self.persist_path:
            return
        try:
            import json
            import os
            if not os.path.exists(self.persist_path):
                return
            with open(self.persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for sid, s in data.get("seeds", {}).items():
                seed = StorySeed(
                    id=s["id"], concept=s["concept"], source=s.get("source", ""),
                    planted_at=s.get("planted_at", time.time()),
                    growth=s.get("growth", 0), growth_rate=s.get("growth_rate", 0.1),
                    watered=s.get("watered", 0),
                    branches=s.get("branches", []), tags=s.get("tags", []),
                    status=s.get("status", "planted"),
                    parent_seed_id=s.get("parent_seed_id", ""),
                    related_seeds=s.get("related_seeds", []),
                )
                self.seeds[sid] = seed

            for tid, t in data.get("threads", {}).items():
                thread = StoryThread(
                    id=t["id"], seed_id=t["seed_id"], title=t["title"],
                    synopsis=t["synopsis"], beats=t.get("beats", []),
                    current_beat=t.get("current_beat", 0),
                    characters=t.get("characters", []),
                    genre=t.get("genre", "None"),
                    tension=t.get("tension", 0),
                    planted_at=t.get("planted_at", time.time()),
                    last_nurtured=t.get("last_nurtured", time.time()),
                    ready_to_fruit=t.get("ready_to_fruit", False),
                    fruited=t.get("fruited", False),
                    fruit_event_type=t.get("fruit_event_type", "narration"),
                )
                self.threads[tid] = thread

            logger.info(f"[Garden] Loaded {len(self.seeds)} seeds, {len(self.threads)} threads from disk")
        except Exception as e:
            logger.debug(f"[Garden] Load failed: {e}")


# ── Director Daemon ─────────────────────────────────────────────────────────

class DirectorDaemon:
    """
    The off-scene AI Director.

    It watches the conversation, plans events, and triggers them through
    the WebSocket server. It's like a film director + dungeon master + improv coach.
    """

    def __init__(
        self,
        ws_server: Any = None,
        memory_client: Any = None,
        llm_client: Any = None,
        min_interval: float = 600.0,
        max_interval: float = 1800.0,
        enabled: bool = True,
    ):
        self.ws = ws_server
        self.memory = memory_client
        self.llm = llm_client
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.enabled = enabled

        # State
        self._event_queue: list[EventPlan] = []
        self._last_event_time = time.time()
        self._next_event_time = time.time() + random.uniform(min_interval, max_interval)
        self._current_event: Optional[EventPlan] = None
        self._conversation_summary: str = ""
        self._user_mood: str = "neutral"
        self._time_of_day: str = ""
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Genre preferences
        self.allow_horror = True
        self.allow_violence = True
        self.allow_surreal = True

        # Plot memory — the Director remembers what's happened
        self._plot_history: list[dict] = []
        self._max_plot_memory = 50

        # Story Garden — the Director's slow-cooking narrative engine
        # Seeds planted today may fruit weeks from now
        import os
        garden_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "story_garden.json"
        )
        self.garden = StoryGarden(persist_path=garden_path)

        # Garden maintenance schedule
        self._last_garden_grow = time.time()
        self._last_seed_plant = time.time()
        self._last_thread_advance = time.time()

        # Character roster — recurring characters the Director can use
        self._character_roster = [
            {"name": "The Stranger", "personality": "mysterious", "voice": "low", "color": "#4a4a6a"},
            {"name": "Detective Vance", "personality": "noir", "voice": "gravel", "color": "#8a7a5a"},
            {"name": "Captain Reyes", "personality": "military", "voice": "commanding", "color": "#6a8a6a"},
            {"name": "Dr. Okafor", "personality": "scientific", "voice": "calm", "color": "#5a8a9a"},
            {"name": "Old Maria", "personality": "warm", "voice": "gentle", "color": "#aa7a6a"},
            {"name": "The Courier", "personality": "urgent", "voice": "fast", "color": "#9a9a5a"},
            {"name": "Eve", "personality": "charming", "voice": "smooth", "color": "#aa5a8a"},
            {"name": "The Kid", "personality": "energetic", "voice": "young", "color": "#5aaa5a"},
        ]

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        """Start the Director daemon."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[Director] Daemon started — the show must go on")

    async def stop(self):
        """Stop the Director daemon."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[Director] Daemon stopped")

    # ── Main Loop ────────────────────────────────────────────────────────────

    async def _run_loop(self):
        """Main Director loop — watches, plans, triggers."""
        while self._running:
            try:
                await asyncio.sleep(10)  # check every 10 seconds

                if not self.enabled:
                    continue

                # Update context
                await self._update_context()

                # Check if it's time for an event
                now = time.time()
                if self._current_event is None and now >= self._next_event_time:
                    # First: check if any story garden seeds are ready to fruit
                    # These take priority — they've been brewing for days
                    mature_seeds = self.garden.get_mature_seeds()
                    ready_threads = self.garden.get_ready_threads()

                    if ready_threads:
                        # A story thread is ready — fruit it as a full event
                        thread = ready_threads[0]
                        await self._fruit_story_thread(thread)
                        self._last_event_time = time.time()
                        self._next_event_time = time.time() + random.uniform(
                            self.min_interval, self.max_interval
                        )
                    elif mature_seeds and random.random() < 0.6:
                        # A mature seed is ready — develop and fruit it
                        seed = mature_seeds[0]
                        thread = self.garden.develop_thread(seed.id)
                        if thread:
                            await self._fruit_story_thread(thread)
                        else:
                            # Fruit directly as a simple event
                            await self._fruit_seed_directly(seed)
                        self._last_event_time = time.time()
                        self._next_event_time = time.time() + random.uniform(
                            self.min_interval, self.max_interval
                        )
                    elif random.random() < 0.4:
                        # 40% chance of a shared surprise instead of a narrative event
                        # Surprises are lighter — they redirect focus without a full scene
                        await self._trigger_shared_surprise()
                        self._last_event_time = time.time()
                        # Surprises have shorter cooldowns
                        self._next_event_time = time.time() + random.uniform(
                            self.min_interval * 0.5, self.max_interval * 0.5
                        )
                    else:
                        await self._plan_and_trigger_event()

                # ── Tend the Story Garden ──
                # Grow seeds periodically (every hour)
                if now - self._last_garden_grow > 3600:
                    self.garden.grow()
                    self._last_garden_grow = now

                # Plant seeds from conversation (every 30 min)
                if now - self._last_seed_plant > 1800 and self._conversation_summary:
                    seed = self.garden.plant_seed_from_conversation(self._conversation_summary)
                    if seed:
                        # Notify the client that a seed was planted (for UI)
                        if self.ws:
                            await self.ws.broadcast("director.garden.seed", {
                                "concept": seed.concept,
                                "source": seed.source,
                                "stage": seed.stage,
                            })
                    self._last_seed_plant = now

                # Advance story threads (every 2-4 hours, if any growing)
                if now - self._last_thread_advance > random.uniform(7200, 14400):
                    growing_threads = [t for t in self.garden.threads.values()
                                      if not t.fruited and not t.ready_to_fruit]
                    if growing_threads:
                        thread = random.choice(growing_threads)
                        beat = self.garden.advance_thread(thread.id)
                        if beat:
                            logger.info(f"[Garden] Thread '{thread.title}' advanced to beat: {beat['beat']}")
                            # A thread beat can manifest as a subtle foreshadowing
                            if self.ws:
                                await self.ws.broadcast("director.garden.beat", {
                                    "threadTitle": thread.title,
                                    "beat": beat["beat"],
                                    "description": beat["description"],
                                    "tension": beat.get("tension", 0.5),
                                })
                    self._last_thread_advance = now

                # Occasionally cross-pollinate (every 6 hours)
                if now - self._last_garden_grow > 21600 and random.random() < 0.3:
                    self.garden.cross_pollinate()

                # Process event queue — prepare upcoming events
                if len(self._event_queue) < 2:
                    await self._prepare_upcoming_events()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Director] Loop error: {e}", exc_info=True)
                await asyncio.sleep(30)

    # ── Context Gathering ────────────────────────────────────────────────────

    async def _update_context(self):
        """Gather context about the current state for planning."""
        self._time_of_day = self._get_time_of_day()

        # Try to get conversation summary from memory
        if self.memory:
            try:
                summary: str = await self._get_conversation_summary()
                if summary:
                    self._conversation_summary = summary
            except Exception as e:
                logger.debug(f"[Director] Memory unavailable: {e}")

        # Detect mood from recent messages (simplified)
        self._user_mood = self._estimate_mood()

    def _get_time_of_day(self) -> str:
        """Get time of day label."""
        hour = time.localtime().tm_hour
        if 5 <= hour < 8: return "dawn"
        if 8 <= hour < 12: return "morning"
        if 12 <= hour < 17: return "afternoon"
        if 17 <= hour < 20: return "evening"
        if 20 <= hour < 23: return "night"
        return "late_night"

    async def _get_conversation_summary(self) -> str:
        """Get a summary of recent conversations from memory."""
        if not self.memory:
            return ""
        try:
            # Try to get recent memory entries
            if hasattr(self.memory, 'get_recent_summary'):
                return await self.memory.get_recent_summary()
            elif hasattr(self.memory, 'get_context'):
                ctx = await self.memory.get_context()
                return str(ctx)[:500]
        except Exception:
            pass
        return ""

    def _estimate_mood(self) -> str:
        """Estimate user mood from time and context (simplified)."""
        if self._time_of_day == "late_night":
            return random.choice(["tired", "reflective", "calm"])
        elif self._time_of_day == "night":
            return random.choice(["relaxed", "cozy", "thoughtful"])
        elif self._time_of_day == "morning":
            return random.choice(["fresh", "energetic", "curious"])
        return "neutral"

    # ── Event Planning ───────────────────────────────────────────────────────

    async def _fruit_story_thread(self, thread: StoryThread):
        """A story thread has matured — bear fruit as a full narrative event.

        This is the payoff of days or weeks of slow growth. The thread's
        beats have been advancing quietly, and now the full scene unfolds.
        """
        logger.info(f"[Director] Story fruiting: '{thread.title}' "
                     f"(genre={thread.genre}, {len(thread.beats)} beats)")

        # Build an event plan from the thread
        plan = EventPlan(
            event_type=thread.fruit_event_type or "event_sequence",
            payload={
                "genre": thread.genre,
                "threadTitle": thread.title,
                "synopsis": thread.synopsis,
                "characters": thread.characters,
                "beats": thread.beats,
                "finalBeat": thread.beats[-1] if thread.beats else {},
            },
            genre=thread.genre,
            character_name=thread.characters[1] if len(thread.characters) > 1 else "",
            narrator_lines=[
                f"the story that has been growing quietly comes to its moment.",
                thread.synopsis,
                thread.beats[-1].get("description", "the conclusion.") if thread.beats else "the end.",
            ],
            dialogue_lines=[],  # The beats contain the narrative
            duration=300,  # Story fruits are longer — they've been building
            tags=["story_garden", "fruited"],
        )

        # Mark thread as fruited (this also plants follow-up seeds)
        self.garden.fruit_thread(thread.id)

        # Trigger with suspense building — this is a big moment
        await self._trigger_event(plan)

    async def _fruit_seed_directly(self, seed: StorySeed):
        """Fruit a mature seed directly as a simpler event (no full thread)."""
        logger.info(f"[Director] Seed fruiting directly: '{seed.concept}'")

        event_type = self.garden._get_fruit_event(seed)
        genre = seed.tags[0] if seed.tags else "None"

        plan = EventPlan(
            event_type=event_type,
            payload={
                "genre": genre,
                "seedConcept": seed.concept,
                "branches": seed.branches,
                "chosenBranch": random.choice(seed.branches) if seed.branches else "",
            },
            genre=genre,
            narrator_lines=[
                f"something that has been quietly growing finally surfaces.",
                seed.concept,
            ],
            dialogue_lines=[],
            duration=180,
            tags=["story_garden", "direct_fruit"],
        )

        self.garden.fruit_seed(seed.id)
        await self._trigger_event(plan)

    async def _plan_and_trigger_event(self):
        """Plan a new event and trigger it."""
        logger.info("[Director] Planning new event...")

        # Try to use LLM for creative planning
        event_plan: Optional[EventPlan] = None
        if self.llm:
            try:
                event_plan = await self._llm_plan_event()
            except Exception as e:
                logger.debug(f"[Director] LLM planning failed: {e}")

        # Fallback to procedural planning
        if event_plan is None:
            event_plan = self._procedural_plan_event()

        if event_plan:
            await self._trigger_event(event_plan)
            self._last_event_time = time.time()
            self._next_event_time = time.time() + random.uniform(self.min_interval, self.max_interval)

    async def _llm_plan_event(self) -> Optional[EventPlan]:
        """Use the LLM to creatively plan an event."""
        if not self.llm:
            return None

        prompt = self._build_planning_prompt()

        try:
            response = await self.llm.generate(prompt, max_tokens=500, temperature=0.9)
            return self._parse_llm_event(response)
        except Exception as e:
            logger.debug(f"[Director] LLM error: {e}")
            return None

    def _build_planning_prompt(self) -> str:
        """Build the prompt for the LLM to plan an event."""
        genre_options = ["phone_ring", "knock", "genre_shift", "character_arrival",
                        "narration", "celebration", "prop_spawn", "event_sequence"]
        if self.allow_horror:
            genre_options.extend(["horror", "surreal_dream"])
        if self.allow_violence:
            genre_options.extend(["war_drama", "spy_thriller"])

        plot_context = ""
        if self._plot_history:
            recent = self._plot_history[-5:]
            plot_context = "\n".join(f"- {p['summary']}" for p in recent)

        return f"""You are the Director of a VR experience. You orchestrate surprise narrative events.

Current context:
- Time of day: {self._time_of_day}
- User mood: {self._user_mood}
- Recent plot: {plot_context or "just started"}
- Conversation summary: {self._conversation_summary[:200] or "no recent conversation"}

Plan ONE surprise event. Be creative and unexpected. Consider the mood and time.

Respond in JSON:
{{
  "event_type": "phone_ring|knock|genre_shift|character_arrival|narration|celebration|prop_spawn|event_sequence",
  "genre": "None|Horror|WarDrama|NoirMystery|RomanticComedy|SciFi|Fantasy|SurrealDream|GameShow",
  "character_name": "name if character_arrival, else empty",
  "narrator_intro": "one line the narrator says to set the scene",
  "dialogue": ["line 1", "line 2", "line 3"],
  "alice_reaction": "how Alice reacts",
  "duration": 120
}}

Be surprising. Be fun. Make it memorable."""

    def _parse_llm_event(self, response: str) -> Optional[EventPlan]:
        """Parse LLM response into an EventPlan."""
        try:
            # Find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= 0:
                return None
            data = json.loads(response[start:end])

            return EventPlan(
                event_type=data.get("event_type", "narration"),
                payload={
                    "genre": data.get("genre", "None"),
                    "character_name": data.get("character_name", ""),
                    "narrator_intro": data.get("narrator_intro", ""),
                    "alice_reaction": data.get("alice_reaction", ""),
                },
                genre=data.get("genre", "None"),
                character_name=data.get("character_name", ""),
                dialogue_lines=data.get("dialogue", []),
                narrator_lines=[data.get("narrator_intro", "")] if data.get("narrator_intro") else [],
                duration=float(data.get("duration", 180)),
                tags=["llm_generated"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"[Director] Parse error: {e}")
            return None

    def _procedural_plan_event(self) -> EventPlan:
        """Procedurally generate an event plan (no LLM)."""
        # Weight events by time of day and mood
        weights = {
            "phone_ring": 15,
            "knock": 10,
            "genre_shift": 8,
            "character_arrival": 12,
            "narration": 15,
            "celebration": 8,
            "prop_spawn": 10,
            "event_sequence": 5,
            "atmosphere_shift": 10,
        }

        # Late night favors horror and surreal
        if self._time_of_day == "late_night" and self.allow_horror:
            weights["genre_shift"] = 15
        # Morning favors celebration and character arrival
        if self._time_of_day == "morning":
            weights["celebration"] = 15
            weights["character_arrival"] = 18

        # Pick event type
        event_types = list(weights.keys())
        weight_values = [weights[e] for e in event_types]
        event_type = random.choices(event_types, weights=weight_values, k=1)[0]

        # Build the plan
        plan = EventPlan(
            event_type=event_type,
            payload={},
            duration=random.uniform(120, 300),
        )

        # Add genre if genre_shift
        if event_type == "genre_shift":
            genres = ["NoirMystery", "SciFi", "RomanticComedy", "Western", "SpyThriller"]
            if self.allow_horror:
                genres.append("Horror")
            if self.allow_violence:
                genres.append("WarDrama")
            if self.allow_surreal:
                genres.append("SurrealDream")
            plan.genre = random.choice(genres)
            plan.payload["genre"] = plan.genre

        # Add character if character_arrival
        if event_type in ("character_arrival", "phone_ring", "event_sequence"):
            char = random.choice(self._character_roster)
            plan.character_name = char["name"]
            plan.payload["character_name"] = char["name"]
            plan.payload["character_personality"] = char["personality"]
            plan.payload["character_voice"] = char["voice"]

        # Generate narrator lines
        plan.narrator_lines = self._generate_narrator_lines(event_type, plan.genre, self._time_of_day)
        plan.payload["narrator_lines"] = plan.narrator_lines

        # Generate dialogue
        plan.dialogue_lines = self._generate_dialogue(event_type, plan.character_name)
        plan.payload["dialogue"] = plan.dialogue_lines

        return plan

    def _generate_narrator_lines(self, event_type: str, genre: str, time_of_day: str) -> list:
        """Generate narrator lines for an event."""
        lines = []

        if event_type == "phone_ring":
            lines.append("the room is quiet. too quiet.")
            lines.append("and then— a sound. distant at first. getting closer.")
            lines.append("a phone. ringing. but there's no phone here. or is there?")

        elif event_type == "knock":
            lines.append("a sound. knuckles on wood. someone's at the door.")
            lines.append("another knock. more insistent this time.")

        elif event_type == "genre_shift":
            genre_intros = {
                "Horror": "the lights flicker. something is wrong. you feel it before you see it.",
                "WarDrama": "the year is 1943. you hear distant artillery. the resistance needs you.",
                "NoirMystery": "rain on the window. a dame walks in. she's got trouble written all over her.",
                "RomanticComedy": "it was a tuesday. nothing special about tuesdays. until it wasn't.",
                "SciFi": "star date 2387.4. the station's AI has detected an anomaly.",
                "Fantasy": "the old magic is returning. you can feel it in the air.",
                "Western": "high noon. the dust settles. someone's riding in.",
                "SpyThriller": "your mission, should you choose to accept it... too late. you already have.",
                "SurrealDream": "you're not sure when you fell asleep. the walls are breathing.",
                "GameShow": "ladies and gentlemen! welcome to the show! are you ready to play?",
            }
            lines.append(genre_intros.get(genre, "something is about to change."))

        elif event_type == "character_arrival":
            lines.append("there's someone at the door.")
            lines.append("the door opens slowly.")

        elif event_type == "celebration":
            lines.append("surprise! the Director thought you deserved a moment of joy.")

        elif event_type == "event_sequence":
            lines.append("it begins. quietly. a normal moment.")
            lines.append("but then—")

        elif event_type == "prop_spawn":
            lines.append("something has appeared. it wasn't here before.")

        elif event_type == "narration":
            time_narration = {
                "dawn": "the first light touches the room. a new day. a new story.",
                "morning": "the morning unfolds. anything is possible.",
                "afternoon": "the afternoon stretches out. time slows.",
                "evening": "the light turns golden. the day's story nears its end.",
                "night": "night falls. the room becomes a different place.",
                "late_night": "it's late. the world is quiet. but the story never sleeps.",
            }
            lines.append(time_narration.get(time_of_day, "and so, the story continues."))

        return lines

    def _generate_dialogue(self, event_type: str, character_name: str) -> list:
        """Generate dialogue for an event."""
        if not character_name:
            return []

        dialogue_templates = {
            "phone_ring": [
                f"...hello? can you hear me?",
                f"i've been trying to reach you.",
                f"my name is {character_name}. we need to talk.",
                f"something is coming. you need to be ready.",
            ],
            "character_arrival": [
                f"hello. i'm {character_name}.",
                f"i hope i'm not intruding.",
                f"but we don't have much time.",
            ],
            "event_sequence": [
                f"you need to leave. now.",
                f"i've been looking for you.",
                f"we don't have much time.",
            ],
        }

        return dialogue_templates.get(event_type, [
            f"i'm {character_name}.",
            f"i've been watching.",
            f"it's time.",
        ])

    # ── Event Triggering ─────────────────────────────────────────────────────

    async def _trigger_event(self, plan: EventPlan):
        """Trigger an event through the WebSocket server.

        For high-intensity events, the Director first builds suspense through
        audio-only foreshadowing — the user feels something coming before
        anything visible happens.
        """
        self._current_event = plan
        plan.triggered = True

        logger.info(f"[Director] Triggering event: {plan.event_type} (genre={plan.genre})")

        # ── Suspense Building Phase ──
        # The Director decides whether to foreshadow this event with audio.
        # Horror, war, mystery, and character arrivals get suspense builds.
        # Celebrations and casual narrations don't — they're surprises, not dread.
        suspense_genres = {"Horror", "WarDrama", "NoirMystery", "SpyThriller", "SurrealDream", "Heist"}
        suspense_events = {"phone_ring", "knock", "character_arrival", "event_sequence", "emergency"}

        should_build_suspense = (
            plan.genre in suspense_genres or
            plan.event_type in suspense_events
        )

        if should_build_suspense and self.ws:
            # Send a suspense.build event — the client starts audio-only foreshadowing
            suspense_duration = random.uniform(60, 180)  # 1-3 minutes of pure audio tension
            suspense_intensity = 0.5
            if plan.genre == "Horror":
                suspense_intensity = 0.8
                suspense_duration = random.uniform(120, 300)  # horror builds longer
            elif plan.genre == "WarDrama":
                suspense_intensity = 0.7
            elif plan.event_type == "emergency":
                suspense_intensity = 0.6
                suspense_duration = random.uniform(30, 60)  # emergencies build fast

            logger.info(f"[Director] Building suspense: {suspense_duration:.0f}s at intensity {suspense_intensity}")

            await self.ws.broadcast("director.suspense.build", {
                "intensity": suspense_intensity,
                "duration": suspense_duration,
                "eventType": plan.event_type,
                "genre": plan.genre,
            })

            # Wait for the suspense to build before triggering the actual event
            await asyncio.sleep(suspense_duration)

            # The threshold moment — brief silence before the event
            await self.ws.broadcast("director.suspense.threshold", {
                "text": random.choice(["...now.", "it's here.", "don't move.", "...", "this is it."]),
            })
            await asyncio.sleep(2)

        # Send the event to all clients
        if self.ws:
            await self.ws.broadcast("director.event", {
                "eventType": plan.event_type,
                "genre": plan.genre,
                "characterName": plan.character_name,
                "narratorLines": plan.narrator_lines,
                "dialogue": plan.dialogue_lines,
                "payload": plan.payload,
                "duration": plan.duration,
            })

        # Record in plot history
        self._add_to_plot_history(plan)

        # Schedule event end
        asyncio.create_task(self._end_event_after(plan.duration))

    async def _abort_suspense(self):
        """Abort suspense building — the Director changed their mind."""
        if self.ws:
            await self.ws.broadcast("director.suspense.abort", {})
        logger.info("[Director] Suspense aborted — the moment passed")

    async def _trigger_shared_surprise(self, surprise_type: str = ""):
        """Trigger a shared surprise — an external event that pulls both the
        user and Alice out of conversation into shared observation.

        These are NOT narrative events. They're things that happen in the world:
        a bird lands, rain starts, fireflies appear, a meteor crosses the sky.
        Alice is surprised too — she doesn't know it's coming.

        The magic: shared wonder. Not talking. Just... witnessing together.
        """
        # If no type specified, pick based on time of day and mood
        if not surprise_type:
            surprise_type = self._pick_surprise()

        logger.info(f"[Director] Shared surprise: {surprise_type}")

        if self.ws:
            await self.ws.broadcast("director.surprise", {
                "surpriseType": surprise_type,
                "timeOfDay": self._time_of_day,
                "mood": self._user_mood,
            })

        # Record in plot history
        self._plot_history.append({
            "summary": f"surprise: {surprise_type}",
            "event_type": "shared_surprise",
            "genre": "None",
            "character": "",
            "timestamp": time.time(),
        })
        if len(self._plot_history) > self._max_plot_memory:
            self._plot_history = self._plot_history[-self._max_plot_memory:]

    def _pick_surprise(self) -> str:
        """Pick a surprise type based on context (time, mood, season)."""
        # Time-of-day appropriate surprises
        time_surprises = {
            "dawn": ["BirdOnWindowsill", "CherryPetals", "ButterflySwarm"],
            "morning": ["BirdOnWindowsill", "BubblesAppear", "ButterflySwarm", "WindChimes"],
            "afternoon": ["Fireflies", "BalloonFloatsBy", "CatWandersIn", "BubblesAppear"],
            "evening": ["SunsetBurst", "Fireflies", "DistantMusic", "WindChimes"],
            "night": ["MeteorCrossing", "AuroraFlare", "ISSPassing", "StarShower", "Fireflies", "StrangeLight"],
            "late_night": ["WhaleSong", "ForgottenMusicBox", "StrangeLight", "StarShower", "AuroraFlare"],
        }

        # Mood-based adjustments
        mood_surprises = {
            "tired": ["RainBegins", "WhaleSong", "WindChimes", "ForgottenMusicBox"],
            "reflective": ["RainBegins", "WhaleSong", "StarShower", "MessageInBottle"],
            "calm": ["Fireflies", "CherryPetals", "WindChimes", "ButterflySwarm"],
            "cozy": ["RainBegins", "CatWandersIn", "ForgottenMusicBox", "DistantMusic"],
            "energetic": ["MeteorCrossing", "BubblesAppear", "BalloonFloatsBy", "ButterflySwarm"],
            "curious": ["StrangeLight", "PackageAtDoor", "MessageInBottle", "ISSPassing"],
        }

        # Combine time and mood suggestions
        candidates = time_surprises.get(self._time_of_day, [])
        mood_sugs = mood_surprises.get(self._user_mood, [])
        candidates.extend(mood_sugs)

        # Avoid repeating recent surprises
        recent = [p["summary"] for p in self._plot_history[-10:]]
        fresh = [s for s in candidates if f"surprise: {s}" not in recent]
        if not fresh:
            fresh = candidates

        return random.choice(fresh) if fresh else "Fireflies"

    async def _end_event_after(self, duration: float):
        """End the current event after a duration."""
        await asyncio.sleep(duration)
        if self._current_event:
            logger.info("[Director] Event ended naturally")
            self._current_event = None

    def _add_to_plot_history(self, plan: EventPlan):
        """Add event to plot history for future planning."""
        summary = f"{plan.event_type}"
        if plan.genre != "None":
            summary += f" ({plan.genre})"
        if plan.character_name:
            summary += f" with {plan.character_name}"

        self._plot_history.append({
            "summary": summary,
            "event_type": plan.event_type,
            "genre": plan.genre,
            "character": plan.character_name,
            "timestamp": time.time(),
        })

        # Trim history
        if len(self._plot_history) > self._max_plot_memory:
            self._plot_history = self._plot_history[-self._max_plot_memory:]

    # ── Upcoming Event Preparation ───────────────────────────────────────────

    async def _prepare_upcoming_events(self):
        """Prepare upcoming events in advance (the Director 'builds' scenes)."""
        # The Director works on future events, developing them over time
        # This is where the LLM could flesh out multi-step narratives
        pass  # Events are planned on-demand for now

    # ── Public API ───────────────────────────────────────────────────────────

    def set_birthday(self, month: int, day: int):
        """Set the user's birthday. The Director will plan something special."""
        self._birthday_month = month
        self._birthday_day = day
        logger.info(f"[Director] Birthday set: {month}/{day}")

        # Plant a birthday seed in the garden — it should grow fast
        # and be ready to fruit on the birthday
        seed = self.garden.plant_seed(
            concept="a birthday celebration that surprises you",
            source="birthday",
        )
        # Birthday seeds grow fast — they should be ready in a few days
        seed.growth_rate = 0.5  # very fast growth
        seed.branches = [
            "alice has prepared something quietly",
            "the director organized a surprise party",
            "a mysterious gift arrives",
            "old friends show up unexpectedly",
            "the whole day becomes a story",
        ]
        self.garden._save()
        logger.info(f"[Director] Birthday seed planted with fast growth")

    def check_birthday_approaching(self) -> bool:
        """Check if the birthday is approaching (within 7 days)."""
        if not hasattr(self, '_birthday_month'):
            return False
        import datetime
        now = datetime.datetime.now()
        birthday = datetime.datetime(now.year, self._birthday_month, self._birthday_day)
        if birthday < now:
            birthday = datetime.datetime(now.year + 1, self._birthday_month, self._birthday_day)
        days_until = (birthday - now).days
        return days_until <= 7

    def enable(self):
        self.enabled = True
        self._next_event_time = time.time() + random.uniform(60, 300)  # first event soon
        logger.info("[Director] Enabled")

    def disable(self):
        self.enabled = False
        logger.info("[Director] Disabled")

    def set_preferences(self, allow_horror: bool = True, allow_violence: bool = True,
                        allow_surreal: bool = True):
        self.allow_horror = allow_horror
        self.allow_violence = allow_violence
        self.allow_surreal = allow_surreal

    def trigger_now(self, event_type: str = "", genre: str = "", character_name: str = ""):
        """Manually trigger an event (for testing or Alice-initiated)."""
        plan = EventPlan(
            event_type=event_type or "narration",
            payload={"genre": genre, "character_name": character_name},
            genre=genre or "None",
            character_name=character_name,
            narrator_lines=self._generate_narrator_lines(event_type or "narration", genre, self._time_of_day),
            dialogue_lines=self._generate_dialogue(event_type or "narration", character_name),
            duration=120,
        )
        asyncio.create_task(self._trigger_event(plan))

    def trigger_surprise(self, surprise_type: str = ""):
        """Trigger a shared surprise (for testing or Alice-initiated)."""
        asyncio.create_task(self._trigger_shared_surprise(surprise_type))

    def get_plot_history(self) -> list:
        """Get the Director's plot history."""
        return self._plot_history.copy()

    def get_upcoming_events(self) -> list:
        """Get queued upcoming events."""
        return [p for p in self._event_queue if not p.triggered]
