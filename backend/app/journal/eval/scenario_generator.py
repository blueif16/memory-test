"""
Eval Step 1: LLM generates journal entries + per-day rubrics.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.config import config

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=config.CHAT_MODEL,
    google_api_key=config.GEMINI_API_KEY,
)

SCENARIO_PROMPT = """\
You are generating a realistic test scenario for a personal journal knowledge graph system.

Archetype: {archetype}
Number of days: {num_days}
Start date: {start_date}

Generate a sequence of daily journal entries for a person matching this archetype.
The entries should tell a coherent story with:
- Recurring entities (people, classes, projects, goals, habits, places)
- Events that get mentioned, approach, and pass
- Relationships that evolve (friendships deepen, conflicts arise)
- State changes (goals completed, projects abandoned, events finished)
- Realistic gaps (not every entity mentioned every day)
- Some days with short entries, some with long detailed ones

For each day, also generate a rubric for what a "morning briefing" BEFORE that day's journal
should contain. The rubric has:
- best_if_covered: aspirational items that show deep understanding (sparse, most days empty)
- good_if_covered: bread-and-butter items the system should surface
- problem_if_covered: things that should NOT appear (stale items, resolved things)
- problem_if_not_covered: critical items that MUST appear (upcoming deadlines, recent important events)

Output as JSON with this structure:
{{
  "archetype": "{archetype}",
  "days": [
    {{
      "day": 1,
      "date": "YYYY-MM-DD",
      "journal_entry": "...",
      "rubric": {{
        "best_if_covered": ["..."],
        "good_if_covered": ["..."],
        "problem_if_covered": ["..."],
        "problem_if_not_covered": ["..."]
      }}
    }}
  ]
}}
"""


class Rubric(BaseModel):
    best_if_covered: list[str] = Field(default_factory=list)
    good_if_covered: list[str] = Field(default_factory=list)
    problem_if_covered: list[str] = Field(default_factory=list)
    problem_if_not_covered: list[str] = Field(default_factory=list)


class DayEntry(BaseModel):
    day: int
    date: str
    journal_entry: str
    rubric: Rubric


class Scenario(BaseModel):
    archetype: str
    days: list[DayEntry]


def generate_scenario(
    archetype: str = "college_student",
    num_days: int = 30,
    start_date: date | None = None,
) -> dict:
    """Generate test scenario: journal entries + per-day rubrics."""
    start = start_date or date.today()
    prompt = SCENARIO_PROMPT.format(
        archetype=archetype,
        num_days=num_days,
        start_date=start.isoformat(),
    )

    structured_llm = _llm.with_structured_output(Scenario)
    result = structured_llm.invoke(prompt)
    return result.model_dump()
