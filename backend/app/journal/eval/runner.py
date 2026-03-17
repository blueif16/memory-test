"""
Eval Step 2: Automated day-by-day run loop.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.journal.ingest_workflow import run_ingest
from app.journal.extraction import run_extraction
from app.journal.eval.scenario_generator import generate_scenario
from app.journal.eval.judge import judge_scenario
from app.journal.eval.aggregator import aggregate_diagnoses
from app.services.journal_ops import journal_ops
from app.visualization.snapshot import capture_snapshot

logger = logging.getLogger(__name__)


def run_scenario(scenario: dict, user_id: str) -> list[dict]:
    """Execute scenario day by day. Returns per-day results.

    For each day:
    1. Auto-resolve upcoming events where target_date < today
    2. Run extraction pipeline → briefing text
    3. Save graph snapshot
    4. Ingest today's journal entry
    5. Return {day, date, extraction_text, rubric, ingest_result}
    """
    results = []

    for day_data in scenario["days"]:
        day_num = day_data["day"]
        entry_date = day_data["date"]
        journal_entry = day_data["journal_entry"]
        rubric = day_data["rubric"]

        logger.info(f"Day {day_num} ({entry_date})")

        # 1. Auto-resolve past events
        journal_ops.auto_resolve_events(entry_date)

        # 2. Run extraction (morning briefing BEFORE today's journal)
        now = datetime.fromisoformat(entry_date)
        extraction_text = run_extraction(user_id, now)

        # 3. Save graph snapshot
        try:
            snapshot = capture_snapshot(user_id, entry_date)
        except Exception as e:
            logger.warning(f"Snapshot failed: {e}")
            snapshot = None

        # 4. Ingest today's journal entry
        ingest_result = run_ingest(user_id, journal_entry, entry_date)

        results.append({
            "day": day_num,
            "date": entry_date,
            "extraction_text": extraction_text,
            "rubric": rubric,
            "ingest_result": ingest_result,
        })

    return results


def run_eval_loop(archetype: str = "college_student", num_days: int = 30) -> dict:
    """Full eval: generate scenario → run → judge → aggregate."""
    # Generate test data
    scenario = generate_scenario(archetype, num_days)

    # Create a test user
    test_user_id = str(uuid.uuid4())

    # Run day-by-day
    results = run_scenario(scenario, test_user_id)

    # Judge each day
    diagnoses = judge_scenario(results)

    # Aggregate systemic issues
    systemic = aggregate_diagnoses(diagnoses)

    return {
        "archetype": archetype,
        "num_days": num_days,
        "test_user_id": test_user_id,
        "per_day_diagnoses": diagnoses,
        "systemic_issues": systemic,
    }
