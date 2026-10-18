"""
Forge/nursery/nano_evolution.py — Nano Evolutionary Selection
====================================================================
The selective-evolution loop for nano XRL models.

Each individual is a cheap genome (hyperparams + curriculum + seed variant)
that is trained and scored against the quality gate. Better genomes survive,
recombine, and mutate across generations. Because the models are tiny, the
whole loop runs in seconds — a fast iterative evolutionary search.

Genome  : {learning_rate, epochs, seed_variant, curriculum_subset}
Fitness : exact + fuzzy reproduction of seed-decode answers (0..1)

Visualization: ASCII fitness curve + best-of table + evolution_log.json.
"""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import torch

from .nano_evaluate import evaluate, evaluate_genome_compression

SEED_VARIANTS = ["micro", "terse", "full"]
CURRICULUM_STAGES = ["seed_decode", "seed_encode", "rubble_to_principa", "red_thread_weaving", "genome_compression"]
GENOME_STAGE = "genome_compression"


@dataclass
class Genome:
    learning_rate: float = 5e-4
    epochs: int = 1
    seed_variant: str = "micro"
    curriculum: list[str] = field(default_factory=lambda: ["seed_decode"])
    max_new_tokens: int = 32

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Genome":
        return cls(**d)


def random_genome(rng: random.Random) -> Genome:
    return Genome(
        learning_rate=round(rng.choice([1e-3, 5e-4, 2e-4, 1e-4]), 6),
        epochs=rng.choice([1, 2, 3]),
        seed_variant=rng.choice(SEED_VARIANTS),
        curriculum=rng.sample(CURRICULUM_STAGES, k=rng.randint(1, 4)),
    )


def mutate(genome: Genome, rng: random.Random) -> Genome:
    g = copy.deepcopy(genome)
    if rng.random() < 0.5:
        g.learning_rate = round(g.learning_rate * rng.choice([0.5, 1.0, 2.0]), 6)
    if rng.random() < 0.4:
        g.epochs = max(1, min(5, g.epochs + rng.choice([-1, 1])))
    if rng.random() < 0.3:
        g.seed_variant = rng.choice(SEED_VARIANTS)
    if rng.random() < 0.3:
        g.curriculum = rng.sample(CURRICULUM_STAGES, k=rng.randint(1, 4))
    return g


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    return Genome(
        learning_rate=rng.choice([a.learning_rate, b.learning_rate]),
        epochs=rng.choice([a.epochs, b.epochs]),
        seed_variant=rng.choice([a.seed_variant, b.seed_variant]),
        curriculum=rng.choice([a.curriculum, b.curriculum]),
    )


# ── Training + fitness ────────────────────────────────────────────────────────

CORPUS_PATH = Path("/home/lumba/FoveAI/Forge/nursery/corpus/seed_decode.jsonl")


def _train_genome(genome: Genome, workdir: Path) -> str:
    """Train a genome and return the saved model dir.

    The genome's `seed_variant` and `curriculum` now actually shape the
    training corpus, so evolution searches those dimensions too.
    """
    from .xrl_nano_data import build_training_corpus
    from .xrl_nano_train_real import DEFAULT_SNAPSHOT, train

    corpus_path = workdir / f"corpus_{genome.seed_variant}.jsonl"
    build_training_corpus(corpus_path, genome.seed_variant, genome.curriculum)

    out = workdir / f"indiv_lr{genome.learning_rate}_e{genome.epochs}_{genome.seed_variant}"
    train(
        DEFAULT_SNAPSHOT,
        str(corpus_path),
        str(out),
        epochs=genome.epochs,
        max_length=512,
        smoke=False,
        batch_size=8,
        lr=genome.learning_rate,
    )
    return str(out)


def _fitness(genome: Genome, workdir: Path, eval_limit: int) -> float:
    """Train (cheap) then evaluate on the gate matching the genome's curriculum."""
    model_dir = _train_genome(genome, workdir)
    if GENOME_STAGE in genome.curriculum:
        report = evaluate_genome_compression(
            model_dir,
            max_new_tokens=max(genome.max_new_tokens, 256),
            limit=eval_limit,
        )
    else:
        report = evaluate(model_dir, str(CORPUS_PATH), max_new_tokens=genome.max_new_tokens, limit=eval_limit)
    _free()
    return float(report["fitness"])


def _free() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ── Evolution loop ───────────────────────────────────────────────────────────

def evolve(
    generations: int = 3,
    population: int = 4,
    eval_limit: int = 8,
    seed: int = 42,
    workdir: Path | None = None,
) -> list[dict[str, Any]]:
    """Run the selective-evolution loop and return a per-generation log."""
    rng = random.Random(seed)
    workdir = workdir or Path("/tmp/nano-evolution")
    workdir.mkdir(parents=True, exist_ok=True)

    pop = [random_genome(rng) for _ in range(population)]
    log: list[dict[str, Any]] = []

    for gen in range(generations):
        t0 = time.time()
        scores: list[tuple[float, Genome]] = []
        for i, g in enumerate(pop):
            print(f"  [gen {gen} ind {i}/{population-1}] {g.to_dict()}")
            fit = _fitness(g, workdir, eval_limit)
            scores.append((fit, g))
            print(f"      fitness={fit:.3f}")

        scores.sort(key=lambda x: x[0], reverse=True)
        best_fit, best_genome = scores[0]
        mean_fit = sum(s for s, _ in scores) / len(scores)
        log.append({
            "generation": gen,
            "best_fitness": round(best_fit, 3),
            "mean_fitness": round(mean_fit, 3),
            "best_genome": best_genome.to_dict(),
            "elapsed_s": round(time.time() - t0, 1),
        })
        print(f"  ==> gen {gen}: best={best_fit:.3f} mean={mean_fit:.3f} "
              f"({log[-1]['elapsed_s']}s)\n")

        if gen == generations - 1:
            break

        # Selection: keep elite + crossover/mutate to refill population.
        elite = [g for _, g in scores[: max(1, population // 2)]]
        new_pop: list[Genome] = []
        while len(new_pop) < population:
            a = rng.choice(elite)
            b = rng.choice(elite)
            child = crossover(a, b, rng) if rng.random() < 0.7 else copy.deepcopy(a)
            child = mutate(child, rng)
            new_pop.append(child)
        pop = new_pop

    out_log = workdir / "evolution_log.json"
    out_log.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"[saved] {out_log}")
    return log


# ── Visualization ────────────────────────────────────────────────────────────

def visualize(log: list[dict[str, Any]]) -> str:
    """Render an ASCII fitness curve + best-of table."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Fitness over generations")
    lines.append("  " + "-" * 40)
    gens = [e["generation"] for e in log]
    bests = [e["best_fitness"] for e in log]
    means = [e["mean_fitness"] for e in log]

    # Scaled bar chart (0..1 -> 0..20 chars)
    for gen, b, m in zip(gens, bests, means):
        bar_b = "#" * int(round(b * 20))
        bar_m = "." * int(round(m * 20))
        lines.append(f"  gen {gen:2d}  best {bar_b:<20s} {b:.3f}")
        lines.append(f"          mean {bar_m:<20s} {m:.3f}")

    lines.append("")
    lines.append("  Best genome per generation")
    lines.append("  " + "-" * 40)
    for e in log:
        g = e["best_genome"]
        cur = ",".join(g["curriculum"])
        lines.append(
            f"  gen {e['generation']:2d}  lr={g['learning_rate']:.6g} "
            f"ep={g['epochs']} seed={g['seed_variant']:6s} fit={e['best_fitness']:.3f}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--population", type=int, default=4)
    ap.add_argument("--eval-limit", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workdir", default="/tmp/nano-evolution")
    args = ap.parse_args()

    log = evolve(
        generations=args.generations,
        population=args.population,
        eval_limit=args.eval_limit,
        seed=args.seed,
        workdir=Path(args.workdir),
    )
    print(visualize(log))
