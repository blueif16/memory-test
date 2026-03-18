"""
Eval Step 3: LLM judges extraction vs rubric.
"""
from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.config import config

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=config.CHAT_MODEL,
    google_api_key=config.GEMINI_API_KEY,
)

JUDGE_PROMPT = """\
You are evaluating a personal journal knowledge graph system.

Day {day} ({date}):

## Morning Briefing (system output)
{extraction_text}

## Rubric
Best if covered (aspirational): {best_if_covered}
Good if covered (expected): {good_if_covered}
Problem if covered (should NOT appear): {problem_if_covered}
Problem if NOT covered (MUST appear): {problem_if_not_covered}

Evaluate:
1. Which "good_if_covered" items were actually covered?
2. Which "problem_if_not_covered" items are MISSING? (These are critical failures)
3. Which "problem_if_covered" items appeared? (These are false positives)
4. Any "best_if_covered" items present? (Bonus points)
5. Overall quality: score 1-5 and explain why.

Be specific. Quote from the briefing text. Identify the root cause of any failures
(e.g., "entity not linked", "event not extracted", "stale item not pruned").
"""


class JudgeDayResult(BaseModel):
    score: int = Field(ge=1, le=5, description="Overall quality score 1-5")
    covered_good: list[str] = Field(default_factory=list)
    missing_critical: list[str] = Field(default_factory=list)
    false_positives: list[str] = Field(default_factory=list)
    root_cause: str = ""
    explanation: str = ""


def judge_day(day_result: dict) -> dict:
    """LLM compares extraction vs rubric. Returns structured judgement."""
    rubric = day_result["rubric"]
    prompt = JUDGE_PROMPT.format(
        day=day_result["day"],
        date=day_result["date"],
        extraction_text=day_result["extraction_text"],
        best_if_covered=", ".join(rubric.get("best_if_covered", [])) or "None",
        good_if_covered=", ".join(rubric.get("good_if_covered", [])) or "None",
        problem_if_covered=", ".join(rubric.get("problem_if_covered", [])) or "None",
        problem_if_not_covered=", ".join(rubric.get("problem_if_not_covered", [])) or "None",
    )
    structured_llm = _llm.with_structured_output(JudgeDayResult)
    result = structured_llm.invoke(prompt)
    return result.model_dump()


def judge_scenario(results: list[dict]) -> list[dict]:
    """Judge all days in a scenario. Returns list of structured judgements."""
    judgements = []
    for day_result in results:
        try:
            judgement = judge_day(day_result)
            judgements.append(judgement)
        except Exception as e:
            logger.error(f"Judge failed for day {day_result['day']}: {e}")
            judgements.append({
                "score": 0,
                "covered_good": [],
                "missing_critical": [],
                "false_positives": [],
                "root_cause": "",
                "explanation": f"JUDGE ERROR: {e}",
            })
    return judgements
