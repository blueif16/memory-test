"""
LangGraph Workflow - Self-Correcting RAG
========================================

retrieve → grade → (rewrite if poor) → generate
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import StateGraph, END

from app.graph.state import AgentState
from app.config import config

if TYPE_CHECKING:
    from app.core import RAGStore

logger = logging.getLogger(__name__)


def create_workflow(rag: "RAGStore", max_retries: int | None = None, checkpointer=None):
    """
    Create self-correcting RAG workflow from a RAGStore.

    Usage:
        rag = RAGStore(namespace="my_kb")
        workflow = create_workflow(rag)
        result = workflow.invoke({"question": "..."})
    """
    from app.graph.nodes import create_nodes

    nodes = create_nodes(rag)
    _max = max_retries or config.MAX_RETRY

    def should_generate(state):
        if state["grade"] == "yes" or state["retry_count"] >= _max:
            return "generate"
        return "rewrite"

    wf = StateGraph(AgentState)
    wf.add_node("retrieve", nodes["retrieve"])
    wf.add_node("grade", nodes["grade"])
    wf.add_node("rewrite", nodes["rewrite"])
    wf.add_node("generate", nodes["generate"])

    wf.set_entry_point("retrieve")
    wf.add_edge("retrieve", "grade")
    wf.add_conditional_edges("grade", should_generate, {"rewrite": "rewrite", "generate": "generate"})
    wf.add_edge("rewrite", "retrieve")
    wf.add_edge("generate", END)

    return wf.compile(checkpointer=checkpointer)


# Default checkpointer
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(conninfo=config.DATABASE_URL, min_size=1, max_size=10)
    checkpointer = PostgresSaver(pool)
except Exception as e:
    logger.warning(f"PostgresSaver unavailable, conversation persistence disabled: {e}")
    checkpointer = None

# Default workflow using RAGStore + shared checkpointer
from app.core.rag_store import RAGStore

_default_rag = RAGStore(namespace="default")
app = create_workflow(_default_rag, checkpointer=checkpointer)
