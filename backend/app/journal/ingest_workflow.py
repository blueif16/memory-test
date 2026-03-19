"""
Pipeline A — Journal Ingest Workflow (LangGraph)

extract → resolve → update_graph → rebuild_context → END
"""
from __future__ import annotations

import logging
import time

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
    t0 = time.perf_counter()
    prompt = EXTRACT_PROMPT.format(
        entry_date=state["entry_date"],
        diary_entry=state["diary_entry"],
    )
    try:
        structured_llm = get_llm().with_structured_output(ExtractionResult)
        result = structured_llm.invoke(prompt)
        extractions = [e.model_dump() for e in result.extractions]
        logger.info("extract_node completed in %.2fs, found %d entities",
                     time.perf_counter() - t0, len(extractions))
        return {"extractions": extractions, "errors": []}
    except Exception as e:
        logger.error("Extraction failed: %s", e, exc_info=True)
        return {"extractions": [], "errors": [f"extract: {e}"]}


# ── Node: resolve ───────────────────────────────────────────────

def resolve_node(state: IngestState) -> dict:
    """Resolve each extracted mention to an existing domain_item or mark as new."""
    t0 = time.perf_counter()
    resolved = []
    errors = list(state.get("errors", []))
    knobs = state.get("knobs")
    threshold = knobs["entity_resolve_threshold"] if knobs else config.ENTITY_RESOLVE_THRESHOLD
    knobs_dict = knobs if knobs else None

    for ext in state["extractions"]:
        try:
            embedding = get_embeddings().embed_query(ext["mention"])
            candidates = journal_ops.resolve_entity(
                ext["mention"], embedding, state["user_id"], match_count=3,
                knobs=knobs_dict,
            )
            if candidates and candidates[0]["score"] > threshold:
                ext["is_new"] = False
                ext["resolved_id"] = candidates[0]["id"]
            else:
                ext["is_new"] = True
                ext["resolved_id"] = None
        except Exception as e:
            logger.error("Resolve failed for %s: %s", ext["mention"], e, exc_info=True)
            ext["is_new"] = True
            ext["resolved_id"] = None
            errors.append(f"resolve({ext['mention']}): {e}")
        resolved.append(ext)

    logger.info("resolve_node completed in %.2fs, resolved %d entities",
                 time.perf_counter() - t0, len(resolved))
    return {"extractions": resolved, "errors": errors}


# ── Node: update_graph ──────────────────────────────────────────

def update_graph_node(state: IngestState) -> dict:
    """Apply all extracted entities, interactions, events, edges to the graph."""
    t0 = time.perf_counter()
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
            logger.error("update_graph failed for %s: %s", ext["mention"], e, exc_info=True)
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

    logger.info("update_graph_node completed in %.2fs, processed %d entities",
                 time.perf_counter() - t0, processed)
    return {"processed_count": processed, "errors": errors}


# ── Node: rebuild_context ───────────────────────────────────────

def rebuild_context_node(state: IngestState) -> dict:
    """Rebuild stale context_docs for affected items."""
    t0 = time.perf_counter()
    try:
        rebuild_stale_context_docs(state["user_id"])
        logger.info("rebuild_context_node completed in %.2fs", time.perf_counter() - t0)
    except Exception as e:
        logger.error("Context rebuild failed: %s", e, exc_info=True)
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


def run_ingest(user_id: str, content: str, entry_date: str, knobs: dict | None = None) -> dict:
    """Full ingest: save diary entry, run pipeline, return results."""
    t0 = time.perf_counter()
    diary = journal_ops.save_diary_entry(user_id, content, entry_date)

    init_state: dict = {
        "diary_entry": content,
        "diary_id": diary["id"],
        "user_id": user_id,
        "entry_date": entry_date,
        "extractions": [],
        "processed_count": 0,
        "errors": [],
    }
    if knobs:
        init_state["knobs"] = knobs

    result = ingest_app.invoke(init_state)

    elapsed = time.perf_counter() - t0
    logger.info("Ingest pipeline completed in %.2fs: %d entities, %d errors",
                 elapsed, len(result.get("extractions", [])), len(result.get("errors", [])))

    return {
        "diary_id": diary["id"],
        "entities_found": len(result.get("extractions", [])),
        "entities_created": sum(
            1 for e in result.get("extractions", []) if e.get("is_new")
        ),
        "processed_count": result.get("processed_count", 0),
        "errors": result.get("errors", []),
    }
