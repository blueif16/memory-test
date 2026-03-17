"""
Pipeline A — Journal Ingest Workflow (LangGraph)

extract → resolve → update_graph → rebuild_context → END
"""
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from app.config import config
from app.journal.state import IngestState
from app.journal.prompts import EXTRACT_PROMPT
from app.core.providers import get_llm, get_embeddings
from app.services.journal_ops import journal_ops
from app.journal.context_builder import rebuild_stale_context_docs

logger = logging.getLogger(__name__)


# ── Pydantic models for structured extraction ──────────────────

class EventExtraction(BaseModel):
    label: str
    date: str
    detail: str = ""


class RelationExtraction(BaseModel):
    mention: str
    relation: str


class EntityExtraction(BaseModel):
    mention: str
    entity_type: str
    domain: str
    snippet: str
    events: list[EventExtraction] = Field(default_factory=list)
    state_change: str | None = None
    relations: list[RelationExtraction] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    extractions: list[EntityExtraction]


# ── Node: extract ───────────────────────────────────────────────

def extract_node(state: IngestState) -> dict:
    """LLM extracts entity mentions from journal entry."""
    prompt = EXTRACT_PROMPT.format(
        entry_date=state["entry_date"],
        diary_entry=state["diary_entry"],
    )
    try:
        structured_llm = get_llm().with_structured_output(ExtractionResult)
        result = structured_llm.invoke(prompt)
        extractions = [e.model_dump() for e in result.extractions]
        return {"extractions": extractions, "errors": []}
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"extractions": [], "errors": [f"extract: {e}"]}


# ── Node: resolve ───────────────────────────────────────────────

def resolve_node(state: IngestState) -> dict:
    """Resolve each extracted mention to an existing domain_item or mark as new."""
    resolved = []
    errors = list(state.get("errors", []))

    for ext in state["extractions"]:
        try:
            embedding = get_embeddings().embed_query(ext["mention"])
            candidates = journal_ops.resolve_entity(
                ext["mention"], embedding, state["user_id"], match_count=3
            )
            if candidates and candidates[0]["score"] > config.ENTITY_RESOLVE_THRESHOLD:
                ext["is_new"] = False
                ext["resolved_id"] = candidates[0]["id"]
            else:
                ext["is_new"] = True
                ext["resolved_id"] = None
        except Exception as e:
            logger.error(f"Resolve failed for {ext['mention']}: {e}")
            ext["is_new"] = True
            ext["resolved_id"] = None
            errors.append(f"resolve({ext['mention']}): {e}")
        resolved.append(ext)

    return {"extractions": resolved, "errors": errors}


# ── Node: update_graph ──────────────────────────────────────────

def update_graph_node(state: IngestState) -> dict:
    """Apply all extracted entities, interactions, events, edges to the graph."""
    diary_id = state["diary_id"]
    user_id = state["user_id"]
    errors = list(state.get("errors", []))
    processed = 0

    # Build mention→id map for edge creation
    mention_to_id: dict[str, str] = {}

    for ext in state["extractions"]:
        try:
            if ext["is_new"]:
                item = journal_ops.create_domain_item(
                    user_id=user_id,
                    title=ext["mention"],
                    domain=ext["domain"],
                    item_type=ext["entity_type"],
                    summary=ext["snippet"],
                )
                item_id = item["id"]
            else:
                item_id = ext["resolved_id"]

            mention_to_id[ext["mention"]] = item_id

            # Add interaction
            journal_ops.add_interaction(
                domain_item_id=item_id,
                diary_id=diary_id,
                snippet=ext["snippet"],
                noted_at=state["entry_date"],
            )

            # Add upcoming events
            for ev in ext.get("events", []):
                journal_ops.add_upcoming_event(
                    domain_item_id=item_id,
                    label=ev["label"],
                    target_date=ev["date"],
                    detail=ev.get("detail", ""),
                    source_diary_id=diary_id,
                )

            # Handle state changes
            if ext.get("state_change") in ("completed", "abandoned"):
                journal_ops.update_lifecycle(
                    item_id, ext["state_change"], ext["snippet"]
                )

            processed += 1
        except Exception as e:
            logger.error(f"update_graph failed for {ext['mention']}: {e}")
            errors.append(f"update({ext['mention']}): {e}")

    # Create/reinforce edges between co-mentioned entities
    for ext in state["extractions"]:
        src_id = mention_to_id.get(ext["mention"])
        if not src_id:
            continue
        for rel in ext.get("relations", []):
            tgt_id = mention_to_id.get(rel["mention"])
            if tgt_id and tgt_id != src_id:
                try:
                    journal_ops.reinforce_edge(src_id, tgt_id, rel["relation"])
                except Exception as e:
                    errors.append(f"edge({ext['mention']}→{rel['mention']}): {e}")

    return {"processed_count": processed, "errors": errors}


# ── Node: rebuild_context ───────────────────────────────────────

def rebuild_context_node(state: IngestState) -> dict:
    """Rebuild stale context_docs for affected items."""
    try:
        rebuild_stale_context_docs(state["user_id"])
    except Exception as e:
        logger.error(f"Context rebuild failed: {e}")
        errors = list(state.get("errors", []))
        errors.append(f"rebuild_context: {e}")
        return {"errors": errors}
    return {}


# ── Workflow assembly ───────────────────────────────────────────

def create_ingest_workflow():
    wf = StateGraph(IngestState)
    wf.add_node("extract", extract_node)
    wf.add_node("resolve", resolve_node)
    wf.add_node("update_graph", update_graph_node)
    wf.add_node("rebuild_context", rebuild_context_node)

    wf.set_entry_point("extract")
    wf.add_edge("extract", "resolve")
    wf.add_edge("resolve", "update_graph")
    wf.add_edge("update_graph", "rebuild_context")
    wf.add_edge("rebuild_context", END)

    return wf.compile()


ingest_app = create_ingest_workflow()


def run_ingest(user_id: str, content: str, entry_date: str) -> dict:
    """Full ingest: save diary entry, run pipeline, return results."""
    diary = journal_ops.save_diary_entry(user_id, content, entry_date)

    result = ingest_app.invoke({
        "diary_entry": content,
        "diary_id": diary["id"],
        "user_id": user_id,
        "entry_date": entry_date,
        "extractions": [],
        "processed_count": 0,
        "errors": [],
    })

    return {
        "diary_id": diary["id"],
        "entities_found": len(result.get("extractions", [])),
        "entities_created": sum(
            1 for e in result.get("extractions", []) if e.get("is_new")
        ),
        "processed_count": result.get("processed_count", 0),
        "errors": result.get("errors", []),
    }
