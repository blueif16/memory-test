"""
LangGraph state definitions for journal pipelines.
"""
from typing import Any

from typing_extensions import TypedDict, NotRequired


class IngestState(TypedDict):
    diary_entry: str
    diary_id: str
    user_id: str
    entry_date: str  # ISO date YYYY-MM-DD
    extractions: list[dict]
    # Each extraction: {mention, entity_type, domain, is_new, resolved_id,
    #                    snippet, events: [{label, date, detail}],
    #                    state_change: str|None, relations: [{mention, relation}]}
    processed_count: int
    errors: list[str]
    knobs: NotRequired[dict[str, Any]]  # Optional tunable parameters from eval loop
