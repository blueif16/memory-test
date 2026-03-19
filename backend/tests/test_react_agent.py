"""
Tests for the ReAct agent ingest node.

Three scenarios:
1. New entity  → agent calls search_similar_nodes (no match) + create_node
2. Existing entity (high score) → search + update_node_interaction, no create
3. Entity with event + state_change → add_event + update_lifecycle called
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


# ── Helpers ──────────────────────────────────────────────────────

def _make_supabase_mock():
    m = MagicMock()
    m.table.return_value = m
    m.rpc.return_value = m
    m.select.return_value = m
    m.insert.return_value = m
    m.update.return_value = m
    m.eq.return_value = m
    m.lte.return_value = m
    m.order.return_value = m
    m.limit.return_value = m
    m.execute.return_value = MagicMock(data=[], count=0)
    return m


def _tool_call(name, args, tc_id="tc1"):
    return {"name": name, "args": args, "id": tc_id, "type": "tool_call"}


def _ai_message(tool_calls=None, content=""):
    msg = MagicMock()
    msg.tool_calls = tool_calls or []
    msg.content = content
    return msg


# ── Shared state factory ─────────────────────────────────────────

def _state(extractions, diary_id="diary-001", entry_date="2026-03-01"):
    return {
        "user_id": "user-001",
        "entry_date": entry_date,
        "diary_id": diary_id,
        "extractions": extractions,
        "processed_count": 0,
        "errors": [],
    }


# ── Scenario 1: new entity → create_node called ──────────────────

def test_new_entity_creates_node():
    """
    search_similar_nodes returns no candidates → agent must call create_node.
    """
    extraction = {
        "mention": "Acme Project",
        "entity_type": "project",
        "domain": "career",
        "snippet": "Started working on Acme Project today.",
        "events": [],
        "state_change": None,
        "relations": [],
    }
    created_item = {"id": "new-uuid-1234", "title": "Acme Project",
                    "domain": "career", "item_type": "project", "summary": "..."}

    turn1 = _ai_message(tool_calls=[
        _tool_call("search_similar_nodes",
                   {"mention": "Acme Project", "entity_type": "project", "domain": "career"}, "tc1"),
        _tool_call("create_node",
                   {"mention": "Acme Project", "entity_type": "project",
                    "domain": "career", "snippet": "Started working on Acme Project today."}, "tc2"),
    ])
    turn2 = _ai_message(content="Done.")

    with patch("app.services.get_supabase_client", return_value=_make_supabase_mock()), \
         patch("app.core.providers.get_llm") as mock_get_llm, \
         patch("app.core.providers.get_embeddings") as mock_get_emb, \
         patch("app.journal.ingest_workflow.journal_ops") as mock_ops:

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [turn1, turn2]
        mock_get_llm.return_value = mock_llm

        mock_get_emb.return_value.embed_query.return_value = [0.1] * 768

        mock_ops.resolve_entity.return_value = []
        mock_ops.create_domain_item.return_value = created_item
        mock_ops.add_interaction.return_value = {}

        from app.journal.ingest_workflow import react_agent_node
        result = react_agent_node(_state([extraction]))

    assert result["processed_count"] == 1
    assert result["errors"] == []
    mock_ops.create_domain_item.assert_called_once()
    assert mock_ops.create_domain_item.call_args.kwargs["title"] == "Acme Project"
    assert mock_ops.create_domain_item.call_args.kwargs["created_at"] == "2026-03-01"


# ── Scenario 2: high-score match → update_node_interaction ───────

def test_existing_entity_updates_interaction():
    """
    search returns score=0.92 → agent calls update_node_interaction, NOT create_node.
    """
    existing_id = "existing-uuid-5678"
    extraction = {
        "mention": "Sarah",
        "entity_type": "person",
        "domain": "social",
        "snippet": "Had coffee with Sarah again.",
        "events": [],
        "state_change": None,
        "relations": [],
    }

    turn1 = _ai_message(tool_calls=[
        _tool_call("search_similar_nodes",
                   {"mention": "Sarah", "entity_type": "person", "domain": "social"}, "tc1"),
        _tool_call("update_node_interaction",
                   {"item_id": existing_id, "snippet": "Had coffee with Sarah again."}, "tc2"),
    ])
    turn2 = _ai_message(content="Done.")

    with patch("app.services.get_supabase_client", return_value=_make_supabase_mock()), \
         patch("app.core.providers.get_llm") as mock_get_llm, \
         patch("app.core.providers.get_embeddings") as mock_get_emb, \
         patch("app.journal.ingest_workflow.journal_ops") as mock_ops:

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [turn1, turn2]
        mock_get_llm.return_value = mock_llm

        mock_get_emb.return_value.embed_query.return_value = [0.2] * 768

        mock_ops.resolve_entity.return_value = [
            {"id": existing_id, "score": 0.92, "title": "Sarah Chen",
             "item_type": "person", "domain": "social", "summary": "Close friend"}
        ]
        mock_ops.add_interaction.return_value = {}

        from app.journal.ingest_workflow import react_agent_node
        result = react_agent_node(_state([extraction], entry_date="2026-03-02"))

    assert result["processed_count"] == 1
    assert result["errors"] == []
    mock_ops.create_domain_item.assert_not_called()
    mock_ops.add_interaction.assert_called_once()
    assert mock_ops.add_interaction.call_args.kwargs["domain_item_id"] == existing_id


# ── Scenario 3: event + state_change ────────────────────────────

def test_event_and_lifecycle():
    """
    Entity with an event and state_change='completed':
    agent must call add_event and update_lifecycle.
    """
    item_id = "existing-uuid-9999"
    extraction = {
        "mention": "ML Project",
        "entity_type": "project",
        "domain": "career",
        "snippet": "Finished the ML Project — submitted final report.",
        "events": [{"label": "Final submission", "date": "2026-03-05",
                    "detail": "Submit to professor"}],
        "state_change": "completed",
        "relations": [],
    }

    turn1 = _ai_message(tool_calls=[
        _tool_call("search_similar_nodes",
                   {"mention": "ML Project", "entity_type": "project", "domain": "career"}, "tc1"),
        _tool_call("update_node_interaction",
                   {"item_id": item_id,
                    "snippet": "Finished the ML Project — submitted final report."}, "tc2"),
        _tool_call("update_lifecycle",
                   {"item_id": item_id, "status": "completed", "note": ""}, "tc3"),
        _tool_call("add_event",
                   {"item_id": item_id, "label": "Final submission",
                    "target_date": "2026-03-05", "detail": "Submit to professor"}, "tc4"),
    ])
    turn2 = _ai_message(content="Done.")

    with patch("app.services.get_supabase_client", return_value=_make_supabase_mock()), \
         patch("app.core.providers.get_llm") as mock_get_llm, \
         patch("app.core.providers.get_embeddings") as mock_get_emb, \
         patch("app.journal.ingest_workflow.journal_ops") as mock_ops:

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [turn1, turn2]
        mock_get_llm.return_value = mock_llm

        mock_get_emb.return_value.embed_query.return_value = [0.3] * 768

        mock_ops.resolve_entity.return_value = [
            {"id": item_id, "score": 0.88, "title": "Machine Learning Project",
             "item_type": "project", "domain": "career", "summary": "Semester project"}
        ]
        mock_ops.add_interaction.return_value = {}
        mock_ops.update_lifecycle.return_value = {}
        mock_ops.add_upcoming_event.return_value = {}

        from app.journal.ingest_workflow import react_agent_node
        result = react_agent_node(_state([extraction], entry_date="2026-03-03"))

    assert result["processed_count"] == 1
    assert result["errors"] == []
    mock_ops.update_lifecycle.assert_called_once_with(item_id, "completed", None)
    mock_ops.add_upcoming_event.assert_called_once()
    assert mock_ops.add_upcoming_event.call_args.kwargs["label"] == "Final submission"
    assert mock_ops.add_upcoming_event.call_args.kwargs["target_date"] == "2026-03-05"
