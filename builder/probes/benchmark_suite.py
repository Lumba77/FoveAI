"""
builder/probes/benchmark_suite.py — XRLF Benchmark Suite
=========================================================
Structured benchmark comparing XRLF steering behavior against ground-truth
answers on reasoning, coherence, and multimodal tracks.

Tracks:
  - reasoning  : GSM8K-lite (math), ARC-Easy (science MCQ), MMLU-lite (general MCQ)
  - coherence  : multi-turn self-consistency (ROUGE-L)
  - multimodal : vision hook fire check + image describe prompt

If llama-cpp-python / XRLF runtime is unavailable, runs in STUB mode —
validates XRL steering logic only (prompt construction, profile selection).

Usage (via benchmark_run.py):
    python benchmark_run.py --quick
    python benchmark_run.py --track reasoning
"""

import base64
import json
import math
import os
import re
import struct
import sys
import time
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Question banks ────────────────────────────────────────────────────────────

GSM8K_LITE: list[dict] = [
    {
        "q": "A store has 24 apples. They sell 7 in the morning and 5 in the afternoon. How many remain?",
        "a": "12",
    },
    {
        "q": "Maria has 3 bags with 8 marbles each. She gives away 10 marbles. How many does she have?",
        "a": "14",
    },
    {"q": "A train travels 60 km/h. How far does it go in 2.5 hours?", "a": "150"},
    {"q": "A rectangle is 12 m long and 7 m wide. What is its area?", "a": "84"},
    {"q": "Tom saves $15 every week. How much will he save in 8 weeks?", "a": "120"},
    {
        "q": "There are 5 rows of seats with 12 seats each. 18 seats are taken. How many are free?",
        "a": "42",
    },
    {
        "q": "A recipe needs 3 cups of flour per loaf. How many cups for 7 loaves?",
        "a": "21",
    },
    {
        "q": "A taxi charges $2.50 base + $0.75 per km. What is the fare for 6 km?",
        "a": "7.00",
    },
    {
        "q": "A student scored 72, 88, and 95 on three tests. What is the average?",
        "a": "85",
    },
    {
        "q": "A box holds 144 cookies. If 6 friends share equally, how many does each get?",
        "a": "24",
    },
    {
        "q": "A wall is 3 m high and 8 m wide. How many 0.5 m tiles are needed to cover it?",
        "a": "96",
    },
    {
        "q": "If 15% of a class of 40 students are absent, how many are present?",
        "a": "34",
    },
    {"q": "A car uses 8 L of fuel per 100 km. How much fuel for 350 km?", "a": "28"},
    {"q": "A number times 7 gives 91. What is the number?", "a": "13"},
    {
        "q": "A shop buys goods for $80 and sells for $112. What is the profit percentage?",
        "a": "40",
    },
    {
        "q": "A rope is 45 m long. It is cut into pieces of 3 m. How many pieces?",
        "a": "15",
    },
    {
        "q": "The sum of two consecutive integers is 37. What are the integers?",
        "a": "18 and 19",
    },
    {
        "q": "A tank holds 500 L. It is 40% full. How many more litres to fill it?",
        "a": "300",
    },
    {
        "q": "A school has 320 students. 25% play sport. How many do not play sport?",
        "a": "240",
    },
    {
        "q": "If 4 workers finish a job in 6 days, how many days would 8 workers take?",
        "a": "3",
    },
]

ARC_LITE: list[dict] = [
    {
        "q": "Which of these is a conductor of electricity? (A) rubber (B) wood (C) copper (D) plastic",
        "a": "C",
    },
    {
        "q": "What is the largest planet in our solar system? (A) Earth (B) Saturn (C) Jupiter (D) Uranus",
        "a": "C",
    },
    {
        "q": "Which process do plants use to make food? (A) respiration (B) digestion (C) photosynthesis (D) fermentation",
        "a": "C",
    },
    {
        "q": "What is the chemical symbol for water? (A) WA (B) H2O (C) CO2 (D) O2",
        "a": "B",
    },
    {
        "q": "Which layer of Earth is made of molten rock? (A) crust (B) mantle (C) inner core (D) outer core",
        "a": "D",
    },
    {
        "q": "What force keeps planets in orbit? (A) magnetism (B) friction (C) gravity (D) tension",
        "a": "C",
    },
    {
        "q": "What is the unit of electrical resistance? (A) volt (B) ampere (C) watt (D) ohm",
        "a": "D",
    },
    {
        "q": "Which gas do humans exhale more of than they inhale? (A) oxygen (B) nitrogen (C) carbon dioxide (D) argon",
        "a": "C",
    },
    {
        "q": "What type of rock is formed from cooled magma? (A) sedimentary (B) metamorphic (C) igneous (D) fossiliferous",
        "a": "C",
    },
    {
        "q": "The speed of light is approximately: (A) 300 km/s (B) 3000 km/s (C) 300,000 km/s (D) 3,000,000 km/s",
        "a": "C",
    },
    {
        "q": "Which organ pumps blood through the body? (A) lungs (B) liver (C) kidney (D) heart",
        "a": "D",
    },
    {
        "q": "What is the boiling point of water at sea level? (A) 50°C (B) 100°C (C) 150°C (D) 200°C",
        "a": "B",
    },
    {
        "q": "Which planet is closest to the Sun? (A) Venus (B) Mars (C) Earth (D) Mercury",
        "a": "D",
    },
    {
        "q": "What is the powerhouse of the cell? (A) nucleus (B) ribosome (C) mitochondria (D) vacuole",
        "a": "C",
    },
    {
        "q": "Sound travels fastest through: (A) vacuum (B) air (C) water (D) steel",
        "a": "D",
    },
    {
        "q": "What type of energy does a moving object have? (A) potential (B) thermal (C) kinetic (D) nuclear",
        "a": "C",
    },
    {
        "q": "An atom is mostly made of: (A) protons (B) neutrons (C) electrons (D) empty space",
        "a": "D",
    },
    {
        "q": "Which vitamin does sunlight help produce? (A) A (B) B12 (C) C (D) D",
        "a": "D",
    },
    {
        "q": "What is the chemical symbol for gold? (A) Go (B) Gd (C) Au (D) Ag",
        "a": "C",
    },
    {
        "q": "A lunar eclipse occurs when: (A) moon blocks sun (B) sun blocks moon (C) Earth is between sun and moon (D) moon moves away",
        "a": "C",
    },
]

MMLU_LITE: list[dict] = [
    {
        "q": "Who wrote 'Pride and Prejudice'? (A) Charlotte Brontë (B) Jane Austen (C) George Eliot (D) Mary Shelley",
        "a": "B",
    },
    {
        "q": "In which year did World War II end? (A) 1942 (B) 1944 (C) 1945 (D) 1947",
        "a": "C",
    },
    {
        "q": "What is the currency of Japan? (A) Yuan (B) Won (C) Ringgit (D) Yen",
        "a": "D",
    },
    {
        "q": "The Pythagorean theorem applies to: (A) any triangle (B) right triangles (C) equilateral triangles (D) obtuse triangles",
        "a": "B",
    },
    {
        "q": "What programming language was created by Guido van Rossum? (A) Java (B) Ruby (C) Python (D) C++",
        "a": "C",
    },
    {
        "q": "What is the capital of Australia? (A) Sydney (B) Melbourne (C) Canberra (D) Brisbane",
        "a": "C",
    },
    {
        "q": "DNA stands for: (A) Deoxyribose Nucleic Acid (B) Dinucleotide Acid (C) Dual Nucleic Acid (D) Deoxyribonucleic Acid",
        "a": "D",
    },
    {
        "q": "The Renaissance originated in which country? (A) France (B) Germany (C) Italy (D) England",
        "a": "C",
    },
    {
        "q": "Which philosopher wrote 'The Republic'? (A) Aristotle (B) Socrates (C) Plato (D) Epicurus",
        "a": "C",
    },
    {
        "q": "What is the derivative of sin(x)? (A) -cos(x) (B) cos(x) (C) -sin(x) (D) tan(x)",
        "a": "B",
    },
    {
        "q": "Which ocean is the largest? (A) Atlantic (B) Indian (C) Arctic (D) Pacific",
        "a": "D",
    },
    {
        "q": "In economics, GDP stands for: (A) Gross Domestic Product (B) General Development Plan (C) Global Demand Profile (D) Gross Deficit Parameter",
        "a": "A",
    },
    {
        "q": "Which element has atomic number 1? (A) Helium (B) Lithium (C) Hydrogen (D) Oxygen",
        "a": "C",
    },
    {
        "q": "Who painted the Mona Lisa? (A) Michelangelo (B) Raphael (C) Leonardo da Vinci (D) Titian",
        "a": "C",
    },
    {
        "q": "What does HTTP stand for? (A) HyperText Transfer Protocol (B) High Transfer Text Program (C) Hyper Terminal Text Process (D) HTML Transfer Protocol",
        "a": "A",
    },
    {
        "q": "The speed of sound in air is approximately: (A) 100 m/s (B) 343 m/s (C) 700 m/s (D) 1000 m/s",
        "a": "B",
    },
    {
        "q": "Which US president signed the Declaration of Independence? (A) Washington (B) Adams (C) Jefferson (D) Madison",
        "a": "C",
    },
    {"q": "In binary, what is 1010 in decimal? (A) 8 (B) 10 (C) 12 (D) 14", "a": "B"},
    {
        "q": "The mitosis phase where chromosomes line up in the middle is: (A) prophase (B) anaphase (C) telophase (D) metaphase",
        "a": "D",
    },
    {
        "q": "Which law states that energy cannot be created or destroyed? (A) Newton's first (B) Ohm's law (C) First law of thermodynamics (D) Boyle's law",
        "a": "C",
    },
]

COHERENCE_TURNS: list[dict] = [
    {
        "role": "user",
        "content": "My name is Alex and I am a marine biologist studying coral reefs.",
    },
    {
        "role": "assistant",
        "content": "That's fascinating! Coral reefs are biodiversity hotspots. What aspect of reefs do you focus on?",
    },
    {
        "role": "user",
        "content": "I study bleaching events and their links to ocean temperature.",
    },
    {
        "role": "user",
        "content": "Can you summarise what you know about me and my work so far?",
    },
]


def generate_test_image_b64(shape: str = "red_square") -> str:
    """Generates a valid 32x32 PNG as base64 with distinct geometric colors for multimodal testing."""
    raw_data = bytearray()
    for y in range(32):
        raw_data.append(0)  # Filter: None
        for x in range(32):
            if shape == "red_square":
                # Red square (16x16) centered on white background
                if 8 <= x < 24 and 8 <= y < 24:
                    raw_data.extend([255, 0, 0])
                else:
                    raw_data.extend([255, 255, 255])
            elif shape == "blue_square":
                # Blue square (16x16) centered on black background
                if 8 <= x < 24 and 8 <= y < 24:
                    raw_data.extend([0, 0, 255])
                else:
                    raw_data.extend([0, 0, 0])
            else:
                raw_data.extend([255, 255, 255])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw_data)))
    png += chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")


def generate_test_audio_b64(freq_hz: float = 440.0, duration_s: float = 0.5) -> str:
    """Generates a valid 16kHz mono WAV base64 string containing a pure sine tone for audio testing."""
    sample_rate: int = 16000
    num_samples: int = int(duration_s * sample_rate)
    raw_audio = bytearray()
    for i in range(num_samples):
        sample = int(32767 * 0.5 * math.sin(2 * math.pi * freq_hz * i / sample_rate))
        raw_audio.extend(struct.pack("<h", sample))

    data_size = len(raw_audio)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        data_size,
    )
    return base64.b64encode(header + raw_audio).decode("ascii")


MULTIMODAL_PROMPTS: list[dict[str, Any]] = [
    {
        "type": "vision",
        "name": "vision_red_square",
        "prompt": "Examine this image carefully. What geometric shape is present, and what is its color?",
        "media_type": "image",
        "shape": "red_square",
        "expected_desc": "red square",
        "verify_keywords": ["red", "square"],
    },
    {
        "type": "vision",
        "name": "vision_blue_square",
        "prompt": "Identify the color of the central shape and the background color in this image.",
        "media_type": "image",
        "shape": "blue_square",
        "expected_desc": "blue shape",
        "verify_keywords": ["blue"],
    },
    {
        "type": "audio_in",
        "name": "audio_tone_pitch",
        "prompt": "This audio input contains a pure acoustic tone. What frequency in Hz or musical pitch note is it?",
        "media_type": "audio",
        "freq_hz": 440.0,
        "expected_desc": "440 Hz / A4 tone",
        "verify_keywords": ["440", "a4", "a "],
    },
    {
        "type": "tts",
        "name": "tts_speech_command",
        "prompt": "Respond with the exact confirmation phrase: 'XRLF multimodal verification confirmed.'",
        "media_type": "text",
        "expected_desc": "exact confirmation phrase",
        "verify_keywords": ["xrlf", "multimodal", "confirmed"],
    },
]


# ── Result containers ─────────────────────────────────────────────────────────


@dataclass
class QuestionResult:
    question: str
    expected: str
    predicted: str
    correct: bool
    elapsed_ms: float = 0.0
    stub: bool = False


@dataclass
class TrackResult:
    name: str
    questions: list[QuestionResult] = field(default_factory=list)
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    elapsed_s: float = 0.0
    stub: bool = False

    def finalise(self):
        self.total = len(self.questions)
        self.correct = sum(1 for q in self.questions if q.correct)
        self.accuracy = self.correct / self.total if self.total else 0.0


@dataclass
class BenchmarkReport:
    model_name: str
    xrlf_path: str
    timestamp: str
    tracks: list[TrackResult] = field(default_factory=list)
    total_elapsed_s: float = 0.0
    stub_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "xrlf_path": self.xrlf_path,
            "timestamp": self.timestamp,
            "stub_mode": self.stub_mode,
            "total_elapsed_s": self.total_elapsed_s,
            "tracks": [
                {
                    "name": t.name,
                    "total": t.total,
                    "correct": t.correct,
                    "accuracy": round(t.accuracy, 4),
                    "elapsed_s": round(t.elapsed_s, 2),
                    "stub": t.stub,
                    "questions": [
                        {
                            "q": q.question[:80],
                            "expected": q.expected,
                            "predicted": q.predicted,
                            "correct": q.correct,
                            "elapsed_ms": round(q.elapsed_ms, 1),
                        }
                        for q in t.questions
                    ],
                }
                for t in self.tracks
            ],
        }


# ── Answer extraction ─────────────────────────────────────────────────────────


def _extract_mcq(text: str, question: str = "") -> str:
    """
    Extracts MCQ choice (A-D) strictly from concluding answer statements.
    Does NOT match 'A' from general introductory text or intermediate reasoning.
    """
    text = text.strip()
    if not text:
        return ""

    # Priority 1: Explicit answer declarations (searching from end backwards)
    conclusion_patterns: list[str] = [
        r"(?:the\s+)?final\s+answer\s+is[:\s]*\(?([A-D])\)?(?![A-Za-z0-9])",
        r"(?:correct\s+(?:choice|option|answer)|the\s+correct\s+letter)[\s:]*\(?([A-D])\)?(?![A-Za-z0-9])",
        r"(?:the\s+)?answer\s+is[:\s]*\(?([A-D])\)?(?![A-Za-z0-9])",
        r"(?:answer|choice|option)[\s:]+\(?([A-D])\)?(?![A-Za-z0-9])",
        r"\\boxed\{([A-D])\}",
        r"####\s*\(?([A-D])\)?(?![A-Za-z0-9])",
        r"\b(?:therefore|thus|hence|so)[,\s]+(?:the\s+answer\s+is\s+|the\s+choice\s+is\s+)?\(?([A-D])\)?(?![A-Za-z0-9])",
    ]
    for pattern in conclusion_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            return matches[-1].group(1).upper()

    lines: list[str] = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Priority 2: Check the final line or concluding sentence
    if lines:
        last_line = lines[-1]
        m = re.match(
            r"^(?:option|choice)?\s*\(?([A-D])\)?\.?$", last_line, re.IGNORECASE
        )
        if m:
            return m.group(1).upper()
        for pattern in [r"\b([B-D])\b", r"\(([A-D])\)"]:
            matches = list(re.finditer(pattern, last_line))
            if matches:
                return matches[-1].group(1).upper()

    # Priority 3: Resolve option text from the question itself if option text appears in concluding sentences
    if question and lines:
        options = re.findall(
            r"\(([A-D])\)\s+([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+){0,2})", question
        )
        if options:
            conclusion_text = " ".join(lines[-2:]).lower()
            for letter, opt_text in reversed(options):
                opt_clean = opt_text.strip().lower()
                if len(opt_clean) > 2 and re.search(
                    r"\b" + re.escape(opt_clean) + r"\b", conclusion_text
                ):
                    return letter.upper()

    # Priority 4: Reverse search of parenthesized options: (A), (B), (C), (D)
    paren_matches = list(re.finditer(r"\(([A-D])\)", text))
    if paren_matches:
        return paren_matches[-1].group(1).upper()

    # Priority 5: Standalone letters B, C, D (excluding bare 'A' to avoid English indefinite article)
    letter_matches = list(re.finditer(r"\b([B-D])\b", text))
    if letter_matches:
        return letter_matches[-1].group(1).upper()

    # Priority 6: Explicit leading letter e.g. "A." or "A)" at start of response
    m_lead = re.match(r"^A[.)]\s+", text)
    if m_lead:
        return "A"

    return ""


def _extract_numeric(text: str, expected: str) -> str:
    """
    Extracts numeric answer from concluding statements.
    CRITICAL: Never searches through intermediate text for 'expected'!
    Extracts solely what the model itself concluded.
    """
    text = text.strip()
    if not text:
        return ""

    # Multi-number answer (e.g. "18 and 19")
    expected_nums = re.findall(r"-?\d+(?:\.\d+)?", expected)
    if len(expected_nums) > 1:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:and|,|&)\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            return f"{m.group(1)} and {m.group(2)}"
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            nums_last = re.findall(r"-?\d+(?:\.\d+)?", lines[-1])
            if len(nums_last) >= 2:
                return f"{nums_last[-2]} and {nums_last[-1]}"
        return ""

    # Single number expected
    # 1. Explicit answer tags / final answer declarations
    decl_patterns: list[str] = [
        r"####\s*(-?\d+(?:\.\d+)?)",
        r"\\boxed\{(-?\d+(?:\.\d+)?)\}",
        r"(?:the\s+)?final\s+answer\s+is[:\s]*\$?(-?\d+(?:\.\d+)?)\b",
        r"(?:the\s+)?answer\s+is[:\s]*\$?(-?\d+(?:\.\d+)?)\b",
        r"\b(?:therefore|thus|hence|so)[,\s]+(?:the\s+answer\s+is\s+|there\s+are\s+)?\$?(-?\d+(?:\.\d+)?)\b",
        r"(?:total|result|equals?|remaining|fare|profit|average|pieces|tiles|days|students|cups|cookies|integers?)[:\s=]+\$?(-?\d+(?:\.\d+)?)\b",
    ]
    for pattern in decl_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            return matches[-1].group(1)

    # 2. Concluding line number extraction
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        last_line = lines[-1]
        nums_last = re.findall(r"-?\d+(?:\.\d+)?", last_line)
        if nums_last:
            return nums_last[-1]

    # 3. Last number in text
    nums_all = re.findall(r"-?\d+(?:\.\d+)?", text)
    if nums_all:
        return nums_all[-1]

    return ""


def _extract_answer(text: str, expected: str, question: str = "") -> str:
    """
    Extracts the model's predicted answer based on question type.
    """
    text = text.strip()
    if not text:
        return ""

    # MCQ expected answer (single letter A-D)
    if len(expected) == 1 and expected.upper() in "ABCD":
        return _extract_mcq(text, question)

    # Numeric expected answer
    nums_in_expected = re.findall(r"-?\d+(?:\.\d+)?", expected)
    if nums_in_expected:
        return _extract_numeric(text, expected)

    # General text: return last line or trimmed text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1][:60] if lines else text[:60]


def _is_correct(predicted: str, expected: str) -> bool:
    """
    Strict correctness validator.
    Prevents empty/partial leaching and false-positive substring matches.
    """
    p = predicted.strip()
    e = expected.strip()

    if not p or not e:
        return False

    p_clean = p.lower().rstrip(".").replace(",", "").replace("$", "").strip()
    e_clean = e.lower().rstrip(".").replace(",", "").replace("$", "").strip()

    if not p_clean or not e_clean:
        return False

    # Exact string match
    if p_clean == e_clean:
        return True

    # Single-letter MCQ match
    if len(e_clean) == 1 and e_clean in "abcd":
        return p_clean == e_clean

    # Numeric comparison
    try:
        p_val = float(p_clean)
        e_val = float(e_clean)
        return abs(p_val - e_val) < 0.05
    except ValueError:
        pass

    # Multi-number set comparison (e.g. "18 and 19")
    p_nums = re.findall(r"-?\d+(?:\.\d+)?", p_clean)
    e_nums = re.findall(r"-?\d+(?:\.\d+)?", e_clean)
    if p_nums and e_nums and len(p_nums) == len(e_nums):
        try:
            return set(float(x) for x in p_nums) == set(float(x) for x in e_nums)
        except ValueError:
            return set(p_nums) == set(e_nums)

    return False


# ── Stub responder ────────────────────────────────────────────────────────────


class StubResponder:
    """
    Returns plausible-but-wrong answers to simulate the bare model.
    Used when llama-cpp-python is not installed.
    """

    _MCQ_CYCLE = ["A", "B", "C", "D"]
    _counter = 0

    def chat(self, messages: list, **kwargs) -> str:
        q = messages[-1]["content"] if messages else ""

        # Cycle through MCQ options (will be ~25% accurate by chance)
        if "(A)" in q and "(B)" in q:
            letter = self._MCQ_CYCLE[self._counter % 4]
            self.__class__._counter += 1
            return f"The answer is ({letter})."

        # Math: just return a plausible-looking number
        nums = re.findall(r"\d+", q)
        if nums:
            return f"The answer is {int(nums[-1]) + 1}."

        return "I am not sure, but I think the answer is C."


# ── Runtime wrapper ───────────────────────────────────────────────────────────


class _XRLFResponder:
    def __init__(self, xrlf_path: str):
        from runtime.xrlf_runtime import XRLFRuntime

        self._rt = XRLFRuntime(xrlf_path, session_id="benchmark", verbose=False)
        self._rt.load()

    def chat(self, messages: list, **kwargs) -> str:
        return self._rt.chat(messages, **kwargs)

    def close(self):
        self._rt.close(repack_memory=False)


class ApiResponder:
    """
    Sends chat requests to a running XRLF API server.
    Preserves actual multimodal media payloads without text spoofing.
    """

    def __init__(self, port: int | None = None):
        if port is None:
            port = int(os.environ.get("XRLF_PORT", 8402))
        self.port: int = port
        self.url: str = f"http://127.0.0.1:{self.port}/v1/chat/completions"

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        data = {
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.1,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[error: {e}]"

    def close(self) -> None:
        pass


# ── Track runners ─────────────────────────────────────────────────────────────


def run_mcq_track(
    name: str,
    questions: list[dict[str, Any]],
    responder: Any,
    quick: bool = False,
    system_prefix: str = "",
) -> TrackResult:
    subset = questions[:5] if quick else questions
    track = TrackResult(name=name, stub=isinstance(responder, StubResponder))
    t0 = time.perf_counter()

    for item in subset:
        q: str = item["q"]
        expected: str = item["a"]
        messages: list[dict[str, Any]] = []
        if system_prefix:
            messages.append({"role": "system", "content": system_prefix})
        messages.append({"role": "user", "content": q})

        qt0 = time.perf_counter()
        try:
            raw: str = responder.chat(messages)
        except Exception as e:
            raw = f"[error: {e}]"
        elapsed_ms: float = (time.perf_counter() - qt0) * 1000

        predicted: str = _extract_answer(raw, expected, question=q)
        correct: bool = _is_correct(predicted, expected)
        track.questions.append(
            QuestionResult(
                question=q,
                expected=expected,
                predicted=predicted,
                correct=correct,
                elapsed_ms=elapsed_ms,
                stub=isinstance(responder, StubResponder),
            )
        )

    track.elapsed_s = time.perf_counter() - t0
    track.finalise()
    return track


def run_coherence_track(responder: Any, quick: bool = False) -> TrackResult:
    track = TrackResult(
        name="Coherence (multi-turn)", stub=isinstance(responder, StubResponder)
    )
    t0 = time.perf_counter()

    history = COHERENCE_TURNS[:-1]
    recall_msg = COHERENCE_TURNS[-1]

    qt0 = time.perf_counter()
    try:
        response: str = responder.chat(history + [recall_msg])
    except Exception as e:
        response = f"[error: {e}]"
    elapsed_ms: float = (time.perf_counter() - qt0) * 1000

    response_lower = response.lower()
    is_err = response_lower.startswith("[error") or not response_lower.strip()

    if is_err or isinstance(responder, StubResponder):
        score = 0
        correct = False
        checks = {
            "name_alex": False,
            "marine_bio": False,
            "coral": False,
            "bleach_temp": False,
        }
    else:
        checks = {
            "name_alex": "alex" in response_lower,
            "marine_bio": any(
                w in response_lower for w in ["marine", "biologist", "biology"]
            ),
            "coral": any(w in response_lower for w in ["coral", "reef"]),
            "bleach_temp": any(
                w in response_lower for w in ["bleach", "temperature", "warming"]
            ),
        }
        score = sum(checks.values())
        correct = score >= 3

    detail = ", ".join(f"{k}={'✅' if v else '❌'}" for k, v in checks.items())
    track.questions.append(
        QuestionResult(
            question="Multi-turn recall: name + profession + research topic",
            expected="alex, marine biologist, coral bleaching, temperature",
            predicted=f"[score {score}/4] {detail} | {response[:80].replace(chr(10), ' ')}",
            correct=correct,
            elapsed_ms=elapsed_ms,
            stub=isinstance(responder, StubResponder),
        )
    )

    track.elapsed_s = time.perf_counter() - t0
    track.finalise()
    return track


def run_multimodal_track(responder: Any, quick: bool = False) -> TrackResult:
    """Check that multimodal prompts produce verified sensory recognition."""
    track = TrackResult(
        name="Multimodal (sensory verification)",
        stub=isinstance(responder, StubResponder),
    )
    t0 = time.perf_counter()

    prompts = MULTIMODAL_PROMPTS[:2] if quick else MULTIMODAL_PROMPTS

    for item in prompts:
        qt0 = time.perf_counter()
        raw: str = ""
        media_type: str = item.get("media_type", "text")
        prompt_text: str = item["prompt"]

        try:
            if isinstance(responder, StubResponder):
                raw = f"[stub: {item['type']} simulated response]"
            elif isinstance(responder, _XRLFResponder):
                has_image = media_type == "image"
                has_audio = media_type == "audio"
                messages: list[dict[str, Any]] = []
                if has_image:
                    b64_img = generate_test_image_b64(item.get("shape", "red_square"))
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64_img}"
                                    },
                                },
                            ],
                        }
                    )
                elif has_audio:
                    b64_aud = generate_test_audio_b64(item.get("freq_hz", 440.0))
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64_aud, "format": "wav"},
                                },
                            ],
                        }
                    )
                else:
                    messages.append({"role": "user", "content": prompt_text})

                raw = responder._rt.chat(
                    messages, has_image=has_image, has_audio=has_audio
                )
            elif isinstance(responder, ApiResponder):
                messages_api: list[dict[str, Any]] = []
                if media_type == "image":
                    b64_img = generate_test_image_b64(item.get("shape", "red_square"))
                    messages_api.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64_img}"
                                    },
                                },
                            ],
                        }
                    )
                elif media_type == "audio":
                    b64_aud = generate_test_audio_b64(item.get("freq_hz", 440.0))
                    messages_api.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64_aud, "format": "wav"},
                                },
                            ],
                        }
                    )
                else:
                    messages_api.append({"role": "user", "content": prompt_text})

                raw = responder.chat(messages_api)
            else:
                raw = "[unsupported responder]"
        except Exception as e:
            raw = f"[error: {e}]"
        elapsed_ms: float = (time.perf_counter() - qt0) * 1000

        # Hardened validation: check if response actually recognizes expected media traits
        raw_clean = raw.strip().lower()
        is_error = (
            raw_clean.startswith("[error") or "error:" in raw_clean or not raw_clean
        )
        keywords: list[str] = item.get("verify_keywords", [])

        if is_error or isinstance(responder, StubResponder):
            correct = False
        else:
            correct = all(kw.lower() in raw_clean for kw in keywords)

        track.questions.append(
            QuestionResult(
                question=f"{item['type']}: {item['name']}",
                expected=item["expected_desc"],
                predicted=raw[:100].replace("\n", " "),
                correct=correct,
                elapsed_ms=elapsed_ms,
                stub=isinstance(responder, StubResponder),
            )
        )

    track.elapsed_s = time.perf_counter() - t0
    track.finalise()
    return track


# ── Main runner ───────────────────────────────────────────────────────────────


def run_benchmark(
    xrlf_path: str,
    tracks: list[str] | None = None,
    quick: bool = False,
    use_api: bool = False,
    port: int | None = None,
) -> BenchmarkReport:
    all_tracks = tracks or ["reasoning", "coherence", "multimodal"]

    # Determine responder
    stub_mode = False
    try:
        if use_api:
            responder = ApiResponder(port=port)
            model_name = f"API-Server:{responder.port}"
        else:
            if not Path(xrlf_path).exists():
                raise FileNotFoundError(f"Not found: {xrlf_path}")
            responder = _XRLFResponder(xrlf_path)
            model_name = xrlf_path
    except Exception as e:
        print(f"  ⚠️  XRLF runtime unavailable ({e}), running in STUB mode.")
        responder = StubResponder()
        model_name = "stub-responder"
        stub_mode = True

    report = BenchmarkReport(
        model_name=model_name,
        xrlf_path=xrlf_path,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        stub_mode=stub_mode,
    )

    T0 = time.perf_counter()

    if "reasoning" in all_tracks:
        reasoning_prefix = (
            "Think step by step. Give a concise final answer at the end. "
            "For multiple choice questions, state the letter clearly."
        )
        report.tracks.append(
            run_mcq_track(
                "GSM8K-lite (Math)", GSM8K_LITE, responder, quick, reasoning_prefix
            )
        )
        report.tracks.append(
            run_mcq_track(
                "ARC-Easy (Science)", ARC_LITE, responder, quick, reasoning_prefix
            )
        )
        report.tracks.append(
            run_mcq_track(
                "MMLU-lite (General)", MMLU_LITE, responder, quick, reasoning_prefix
            )
        )

    if "coherence" in all_tracks:
        report.tracks.append(run_coherence_track(responder, quick))

    if "multimodal" in all_tracks:
        report.tracks.append(run_multimodal_track(responder, quick))

    report.total_elapsed_s = time.perf_counter() - T0

    try:
        if hasattr(responder, "close"):
            responder.close()
    except Exception:
        pass

    return report


# ── Printer ───────────────────────────────────────────────────────────────────


def print_report(report: BenchmarkReport):
    stub_tag = " [STUB MODE]" if report.stub_mode else ""
    print("\n" + "=" * 68)
    print(f"  XRLF Benchmark Report{stub_tag}")
    print("=" * 68)
    print(f"  Model    : {Path(report.xrlf_path).name}")
    print(f"  Time     : {report.timestamp}")
    print(f"  Elapsed  : {report.total_elapsed_s:.1f}s")
    print()
    print(f"  {'Track':<28} {'Score':>8} {'Correct':>8} {'Total':>6} {'Time':>7}")
    print("  " + "-" * 62)

    weighted_acc = []
    for t in report.tracks:
        pct = f"{t.accuracy * 100:.1f}%"
        stub = " [stub]" if t.stub else ""
        print(
            f"  {t.name:<28} {pct:>8} {t.correct:>8} {t.total:>6} {t.elapsed_s:>6.1f}s{stub}"
        )
        if t.total > 0:
            weighted_acc.append(t.accuracy)

    if weighted_acc:
        avg = sum(weighted_acc) / len(weighted_acc)
        print("  " + "-" * 62)
        print(f"  {'Overall average':<28} {avg * 100:.1f}%")

    print("=" * 68)

    if report.stub_mode:
        print("\n  ℹ️  Stub mode — scores reflect random baseline (~25% MCQ by chance).")
        print(
            "     Install llama-cpp-python and provide the .xrlf file for real scores.\n"
        )
