"""
Autonomous optimization loop for Journal Graph RAG.

Follows the Karpathy autoresearch pattern:
  freeze eval → commit knobs → run eval → measure → decide → repeat
"""
from __future__ import annotations

import csv
import importlib
import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.config import config
from app.journal.eval.knobs import Knobs
from app.journal.eval.metric import compute_metric
from app.journal.eval.scenario_generator import generate_scenario
from app.journal.eval.runner import run_scenario, run_eval_loop
from app.journal.eval.judge import judge_scenario
from app.journal.eval.aggregator import aggregate_diagnoses

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
RESULTS_FILE = EVAL_DIR / "results.tsv"
SCENARIO_CACHE = EVAL_DIR / "scenario_cache.json"
PROGRAM_FILE = EVAL_DIR / "program.md"

_planner_llm = ChatGoogleGenerativeAI(
    model=config.CHAT_MODEL,
    google_api_key=config.GEMINI_API_KEY,
)


# ── Pydantic model for LLM experiment planning ──────────────────

class ExperimentPlan(BaseModel):
    reasoning: str = Field(description="Why this change, based on results so far")
    parameter_changed: str = Field(description="Which knob was changed")
    old_value: str = Field(description="Previous value")
    new_value: str = Field(description="New value")
    knobs: dict = Field(description="Full knobs configuration as a flat dict")


# ── Git helpers ──────────────────────────────────────────────────

def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True, text=True, cwd=str(EVAL_DIR.parents[3]),
    )
    if result.returncode != 0:
        logger.warning(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _git_commit(message: str) -> None:
    _git("add", "-A")
    _git("commit", "-m", message)


def _git_tag(tag: str) -> None:
    _git("tag", "-f", tag)


# ── Knobs I/O ────────────────────────────────────────────────────

def reload_knobs() -> Knobs:
    """Re-import knobs module to pick up file edits."""
    import app.journal.eval.knobs as knobs_mod
    importlib.reload(knobs_mod)
    return knobs_mod.KNOBS


def write_knobs(knobs: Knobs) -> None:
    """Write a new knobs.py file with updated defaults."""
    knobs_path = EVAL_DIR / "knobs.py"
    lines = [
        '"""',
        "Tunable parameters for the Journal Graph RAG system.",
        "This is the ONLY file the optimization agent edits.",
        '"""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, asdict",
        "",
        "",
        "@dataclass",
        "class Knobs:",
    ]

    fields = asdict(knobs)
    for name, value in fields.items():
        if isinstance(value, str):
            lines.append(f'    {name}: str = {value!r}')
        elif isinstance(value, float):
            lines.append(f"    {name}: float = {value}")
        elif isinstance(value, int):
            lines.append(f"    {name}: int = {value}")
        else:
            lines.append(f"    {name} = {value!r}")

    lines.extend([
        "",
        "    def to_dict(self) -> dict:",
        "        return asdict(self)",
        "",
        "",
        "KNOBS = Knobs()",
        "",
    ])
    knobs_path.write_text("\n".join(lines))


def knobs_summary(knobs: Knobs) -> str:
    """One-line summary of non-default knob values."""
    defaults = Knobs()
    diffs = []
    for k, v in asdict(knobs).items():
        default_v = getattr(defaults, k)
        if v != default_v:
            diffs.append(f"{k}={v}")
    return ", ".join(diffs) if diffs else "defaults"


# ── Scenario caching ─────────────────────────────────────────────

def get_or_generate_scenario(
    archetype: str, num_days: int, seed: str | None = None,
) -> dict:
    """Load cached scenario or generate and cache a new one."""
    if SCENARIO_CACHE.exists():
        cached = json.loads(SCENARIO_CACHE.read_text())
        if cached.get("archetype") == archetype and len(cached.get("days", [])) >= num_days:
            logger.info("Using cached scenario")
            return cached

    logger.info(f"Generating new scenario: {archetype}, {num_days} days")
    scenario = generate_scenario(archetype, num_days)
    SCENARIO_CACHE.write_text(json.dumps(scenario, indent=2))
    return scenario


# ── Results logging ──────────────────────────────────────────────

def append_result(
    iteration: int,
    score: float,
    knobs: Knobs,
    summary: str,
) -> None:
    """Append one row to results.tsv."""
    file_exists = RESULTS_FILE.exists()
    with open(RESULTS_FILE, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        if not file_exists:
            writer.writerow(["iteration", "score", "knobs", "summary", "timestamp"])
        writer.writerow([
            iteration,
            f"{score:.3f}",
            json.dumps(asdict(knobs)),
            summary[:200],
            datetime.utcnow().isoformat(),
        ])


# ── LLM experiment planner ───────────────────────────────────────

def plan_next_experiment(
    current_knobs: Knobs,
    current_score: float,
    best_score: float,
) -> Knobs:
    """Ask LLM to propose the next knobs configuration."""
    program_text = PROGRAM_FILE.read_text() if PROGRAM_FILE.exists() else ""
    results_text = RESULTS_FILE.read_text() if RESULTS_FILE.exists() else "No results yet."

    prompt = f"""\
{program_text}

## Current State
- Current score: {current_score:.3f}
- Best score so far: {best_score:.3f}
- Current knobs: {json.dumps(asdict(current_knobs), indent=2)}

## Experiment History
{results_text}

Based on the program instructions and experiment history, propose the next
knobs configuration. Change ONE parameter at a time for clear attribution.
Return the full knobs dict with your change applied.
"""
    structured_llm = _planner_llm.with_structured_output(ExperimentPlan)
    plan = structured_llm.invoke(prompt)

    logger.info(f"Experiment plan: {plan.reasoning}")
    logger.info(f"Changed {plan.parameter_changed}: {plan.old_value} → {plan.new_value}")

    # Build new Knobs from the plan's dict, falling back to current values
    current_dict = asdict(current_knobs)
    new_dict = {**current_dict, **plan.knobs}
    return Knobs(**{k: new_dict[k] for k in current_dict})


# ── Main loop ────────────────────────────────────────────────────

def run_optimization_loop(
    num_iterations: int = 10,
    archetype: str = "college_student",
    num_days: int = 30,
) -> dict:
    """Run the full optimization loop.

    Returns dict with best_score, best_knobs, and all results.
    """
    # 1. Freeze the scenario
    scenario = get_or_generate_scenario(archetype, num_days)

    best_score = -1.0
    best_knobs = Knobs()
    all_results = []

    for i in range(num_iterations):
        logger.info(f"=== Iteration {i} ===")

        # 2. Load current knobs
        knobs = reload_knobs()
        knobs_dict = knobs.to_dict()

        # 3. Git commit the knobs
        _git_commit(f"experiment-{i}: {knobs_summary(knobs)}")

        # 4. Create a fresh test user and run scenario
        test_user_id = str(uuid.uuid4())
        from app.journal.eval.runner import run_scenario as _run_scenario
        results = _run_scenario(scenario, test_user_id, knobs=knobs_dict)

        # 5. Judge
        judgements = judge_scenario(results)

        # 6. Compute metric
        score = compute_metric(judgements)
        logger.info(f"Score: {score:.3f} (best: {best_score:.3f})")

        # 7. Aggregate for human-readable summary
        summary = aggregate_diagnoses(judgements)

        # 8. Log result
        append_result(i, score, knobs, summary)
        all_results.append({
            "iteration": i,
            "score": score,
            "knobs": knobs_dict,
            "summary": summary[:500],
        })

        # 9. Track best
        if score > best_score:
            best_score = score
            best_knobs = knobs
            _git_tag(f"best-{score:.3f}")
            logger.info(f"New best: {score:.3f}")

        # 10. Plan next experiment (skip on last iteration)
        if i < num_iterations - 1:
            next_knobs = plan_next_experiment(knobs, score, best_score)
            write_knobs(next_knobs)

    # Final commit
    _git_commit(f"optimization complete: best={best_score:.3f}")

    return {
        "best_score": best_score,
        "best_knobs": asdict(best_knobs),
        "iterations": len(all_results),
        "results": all_results,
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run optimization loop")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--archetype", default="college_student")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    result = run_optimization_loop(
        num_iterations=args.iterations,
        archetype=args.archetype,
        num_days=args.days,
    )
    print(f"\nBest score: {result['best_score']:.3f}")
    print(f"Best knobs: {json.dumps(result['best_knobs'], indent=2)}")
