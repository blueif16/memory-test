"""
LangGraph state definitions for journal pipelines.
"""
from typing_extensions import TypedDict


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
