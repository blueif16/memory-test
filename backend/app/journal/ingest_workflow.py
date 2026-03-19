"""
Pipeline A — Journal Ingest Workflow (LangGraph)

extract → react_agent → rebuild_context → END

The react_agent node is a tool-calling ReAct agent that sees the existing
graph and decides per-entity whether to merge, create, or update — replacing
the old dumb resolve+update_graph linear pipeline.
"""
from __future__ import annotations

import json
import logging
import time

from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from app.config import config
from app.journal.state import IngestState
from app.journal.prompts import EXTRACT_PROMPT, build_react_agent_prompt
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
        logger.error("extract_node failed: %s", e, exc_info=True)
        return {"extractions": [], "errors": [f"extract: {e}"]}


# ── Node: react_agent ───────────────────────────────────────────

def react_agent_node(state: IngestState) -> dict:
    """
    ReAct agent that processes all extracted entities against the live graph.
    For each entity it searches for similar nodes, then decides to merge or
    create, adds interactions, events, lifecycle updates, and edges.
    Replaces the old resolve_node + update_graph_node pair.
    """
    t0 = time.perf_counter()
    user_id = state["user_id"]
    entry_date = state["entry_date"]
    diary_id = state["diary_id"]
    extractions = state["extractions"]
    knobs = state.get("knobs")
    errors = list(state.get("errors", []))

    if not extractions:
        logger.info("react_agent_node: no extractions to process")
        return {"processed_count": 0, "errors": errors}

    # ── Tools (closures over state) ──────────────────────────────

    @tool
    def search_similar_nodes(mention: str, entity_type: str, domain: str) -> str:
        """Search for existing graph nodes similar to this entity mention.
        Returns up to 5 candidates with id, title, score, item_type, domain, summary.
        ALWAYS call this before create_node."""
        try:
            embedding = get_embeddings().embed_query(mention)
            candidates = journal_ops.resolve_entity(
                mention, embedding, user_id,
                match_count=knobs.get("match_count", 5) if knobs else 5,
                knobs=knobs,
            )
            if not candidates:
                return "No similar nodes found."
            lines = []
            for c in candidates:
                summary_preview = (c.get("summary") or "")[:120]
                lines.append(
                    f"id={c['id']} score={c['score']:.3f} "
                    f"title={c['title']!r} type={c.get('item_type','?')} "
                    f"domain={c.get('domain','?')} summary={summary_preview!r}"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error("search_similar_nodes error: %s", e)
            return f"Error: {e}"

    @tool
    def create_node(mention: str, entity_type: str, domain: str, snippet: str) -> str:
        """Create a new domain item node in the graph.
        Only call this after search_similar_nodes confirms no match with score >= 0.75.
        Returns the new node id."""
        try:
            item = journal_ops.create_domain_item(
                user_id=user_id,
                title=mention,
                domain=domain,
                item_type=entity_type,
                summary=snippet,
                created_at=entry_date,
            )
            journal_ops.add_interaction(
                domain_item_id=item["id"],
                diary_id=diary_id,
                snippet=snippet,
                noted_at=entry_date,
            )
            return f"Created node id={item['id']} title={mention!r}"
        except Exception as e:
            logger.error("create_node error: %s", e)
            return f"Error: {e}"

    @tool
    def update_node_interaction(item_id: str, snippet: str) -> str:
        """Record a new journal mention for an existing node (merge path).
        Call this when search_similar_nodes returns a match with score >= 0.75."""
        try:
            journal_ops.add_interaction(
                domain_item_id=item_id,
                diary_id=diary_id,
                snippet=snippet,
                noted_at=entry_date,
            )
            return f"Interaction added to node id={item_id}"
        except Exception as e:
            logger.error("update_node_interaction error: %s", e)
            return f"Error: {e}"

    @tool
    def update_lifecycle(item_id: str, status: str, note: str = "") -> str:
        """Mark a node as 'completed' or 'abandoned'.
        Use when the journal clearly indicates the entity is finished or dropped."""
        try:
            journal_ops.update_lifecycle(item_id, status, note or None)
            return f"Node {item_id} lifecycle set to {status!r}"
        except Exception as e:
            logger.error("update_lifecycle error: %s", e)
            return f"Error: {e}"

    @tool
    def add_event(item_id: str, label: str, target_date: str, detail: str = "") -> str:
        """Add an upcoming event (deadline, meeting, launch, etc.) to a node."""
        try:
            journal_ops.add_upcoming_event(
                domain_item_id=item_id,
                label=label,
                target_date=target_date,
                detail=detail,
                source_diary_id=diary_id,
            )
            return f"Event '{label}' on {target_date} added to node {item_id}"
        except Exception as e:
            logger.error("add_event error: %s", e)
            return f"Error: {e}"

    @tool
    def add_edge(source_id: str, target_id: str, relation: str) -> str:
        """Create or strengthen a relationship edge between two graph nodes.
        Call after both endpoint nodes have been resolved or created."""
        try:
            journal_ops.upsert_edge(source_id, target_id, relation)
            return f"Edge {source_id} -[{relation}]-> {target_id} upserted"
        except Exception as e:
            logger.error("add_edge error: %s", e)
            return f"Error: {e}"

    all_tools = [
        search_similar_nodes,
        create_node,
        update_node_interaction,
        update_lifecycle,
        add_event,
        add_edge,
    ]
    tools_by_name = {t.name: t for t in all_tools}
    llm_with_tools = get_llm().bind_tools(all_tools)

    # ── Build initial messages ───────────────────────────────────
    # Allow knobs to override the merge/create decision rules
    agent_merge_rules = knobs.get("agent_merge_rules") if knobs else None
    system_prompt = build_react_agent_prompt(agent_merge_rules or None)

    extractions_json = json.dumps(extractions, indent=2)
    human_content = (
        f"Entry date: {entry_date}\n\n"
        f"Extracted entities from today's journal entry:\n{extractions_json}\n\n"
        "Process every entity above following the rules in your system prompt.\n"
        "Work through them one by one. After all entities are processed, "
        "add edges for all relations using the node ids you collected."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_content),
    ]

    # ── ReAct loop ───────────────────────────────────────────────
    MAX_ITERATIONS = 60  # safety cap (50 entities * ~1-2 LLM calls each)
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            logger.error("react_agent_node LLM call failed at iteration %d: %s", iteration, e)
            errors.append(f"react_agent llm iter={iteration}: {e}")
            break

        # Strip Gemini's signature metadata before re-appending — it causes
        # pydantic validation errors when the message is sent back to the API
        if hasattr(response, "additional_kwargs") and response.additional_kwargs:
            response.additional_kwargs.clear()
        messages.append(response)

        if not response.tool_calls:
            # Agent finished
            break

        # Execute every tool call
        for tc in response.tool_calls:
            tool_fn = tools_by_name.get(tc["name"])
            if tool_fn is None:
                result_content = f"Unknown tool: {tc['name']}"
                logger.warning("Agent called unknown tool: %s", tc["name"])
            else:
                try:
                    result_content = str(tool_fn.invoke(tc["args"]))
                except Exception as e:
                    result_content = f"Tool error: {e}"
                    errors.append(f"tool({tc['name']}): {e}")
                    logger.error("Tool %s failed: %s", tc["name"], e)

            messages.append(
                ToolMessage(content=result_content, tool_call_id=tc["id"])
            )

    elapsed = time.perf_counter() - t0
    logger.info(
        "react_agent_node done in %.2fs, %d LLM iterations, %d entities, %d errors",
        elapsed, iteration, len(extractions), len(errors),
    )

    # Mark all extractions as processed (downstream rebuild_context only needs user_id)
    updated_extractions = [
        {**e, "is_new": True, "resolved_id": None} for e in extractions
    ]
    return {
        "extractions": updated_extractions,
        "processed_count": len(extractions),
        "errors": errors,
    }


# ── Node: rebuild_context ────────────────────────────────────────

def rebuild_context_node(state: IngestState) -> dict:
    """Rebuild context documents for stale domain items."""
    try:
        rebuild_stale_context_docs(state["user_id"])
    except Exception as e:
        logger.error("rebuild_context_node failed: %s", e, exc_info=True)
        errors = list(state.get("errors", []))
        errors.append(f"rebuild_context: {e}")
        return {"errors": errors}
    return {}


# ── Workflow assembly ───────────────────────────────────────────

def create_ingest_workflow():
    wf = StateGraph(IngestState)
    wf.add_node("extract", extract_node)
    wf.add_node("react_agent", react_agent_node)
    wf.add_node("rebuild_context", rebuild_context_node)

    wf.set_entry_point("extract")
    wf.add_edge("extract", "react_agent")
    wf.add_edge("react_agent", "rebuild_context")
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
    logger.info(
        "Ingest pipeline completed in %.2fs: %d entities processed, %d errors",
        elapsed,
        result.get("processed_count", 0),
        len(result.get("errors", [])),
    )

    # Capture snapshot after ingest
    try:
        from app.visualization.snapshot import capture_snapshot
        capture_snapshot(user_id, entry_date)
        logger.info("Snapshot captured for %s on %s", user_id, entry_date)
    except Exception as e:
        logger.error("Failed to capture snapshot for %s on %s: %s", user_id, entry_date, e)

    return {
        "diary_id": diary["id"],
        "entities_found": len(result.get("extractions", [])),
        "processed_count": result.get("processed_count", 0),
        "errors": result.get("errors", []),
    }
