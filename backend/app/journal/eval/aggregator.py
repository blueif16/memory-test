"""
Eval Step 4: Aggregate per-day diagnoses into systemic issues.
"""
from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import config

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=config.CHAT_MODEL,
    google_api_key=config.GEMINI_API_KEY,
)

AGGREGATE_PROMPT = """\
You are analyzing the results of a journal knowledge graph evaluation run.
Below are per-day diagnoses from a {num_days}-day test scenario.

{diagnoses_text}

Identify SYSTEMIC issues — patterns that repeat across multiple days.
For each issue:
1. Name it clearly (e.g., "Entity resolution too aggressive", "Events not pruned after passing")
2. Which days it affected
3. Root cause hypothesis pointing to a specific pipeline component:
   - extract_node: LLM extraction prompt issues
   - resolve_node: entity matching threshold or embedding quality
   - update_graph_node: edge/interaction/event creation logic
   - rebuild_context_node: context_doc assembly
   - score_domain_items: SQL scoring weights
   - extract_briefing_data: SQL extraction or format_briefing output
4. Suggested fix

Rank issues by severity (how many days affected × how critical the failures).
Be actionable. Point to specific code/SQL components.
"""


def aggregate_diagnoses(diagnoses: list[dict | str], num_days: int | None = None) -> str:
    """LLM reads all diagnoses, identifies systemic issues.

    Accepts either plain-text strings (legacy) or structured dicts with
    an 'explanation' key (new judge output).
    """
    num_days = num_days or len(diagnoses)

    def _to_text(d: dict | str) -> str:
        if isinstance(d, dict):
            parts = [f"Score: {d.get('score', '?')}/5"]
            if d.get("covered_good"):
                parts.append(f"Covered good: {', '.join(d['covered_good'])}")
            if d.get("missing_critical"):
                parts.append(f"Missing critical: {', '.join(d['missing_critical'])}")
            if d.get("false_positives"):
                parts.append(f"False positives: {', '.join(d['false_positives'])}")
            if d.get("root_cause"):
                parts.append(f"Root cause: {d['root_cause']}")
            if d.get("explanation"):
                parts.append(d["explanation"])
            return "\n".join(parts)
        return str(d)

    diagnoses_text = "\n\n---\n\n".join(
        f"### Day {i + 1}\n{_to_text(d)}" for i, d in enumerate(diagnoses)
    )
    prompt = AGGREGATE_PROMPT.format(
        num_days=num_days,
        diagnoses_text=diagnoses_text,
    )
    result = _llm.invoke(prompt)
    return result.content
