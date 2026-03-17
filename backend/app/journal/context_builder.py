"""
Context doc rebuilder — assembles rich context from interactions, events,
and edges, then embeds and stores.
"""
from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import config
from app.journal.prompts import CONTEXT_DOC_PROMPT
from app.core.gemini_embeddings import GeminiEmbeddings
from app.services.journal_ops import journal_ops

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(
    model=config.CHAT_MODEL,
    google_api_key=config.GEMINI_API_KEY,
)
_emb = GeminiEmbeddings(
    model=config.EMBEDDING_MODEL,
    output_dimensionality=config.EMBEDDING_DIM,
)


def rebuild_stale_context_docs(user_id: str) -> int:
    """Rebuild context_doc for all stale items. Returns count rebuilt."""
    stale_items = journal_ops.get_stale_items(user_id)
    rebuilt = 0

    for item in stale_items:
        try:
            _rebuild_single(item)
            rebuilt += 1
        except Exception as e:
            logger.error(f"Failed to rebuild context for {item['id']}: {e}")

    return rebuilt


def _rebuild_single(item: dict) -> None:
    """Rebuild context_doc for a single domain item."""
    item_id = item["id"]

    # Gather data
    interactions = journal_ops.get_interactions(item_id, limit=10)
    events = journal_ops.get_events_for_item(item_id)
    edges = journal_ops.get_edges_for_item(item_id)

    # Format for prompt
    interactions_text = "\n".join(
        f"- [{i.get('noted_at', 'unknown')}] {i['snippet']}"
        for i in interactions
    ) or "None"

    events_text = "\n".join(
        f"- {e['label']} ({e['target_date']}) — {e.get('detail', '')}"
        for e in events
        if e.get("status") == "upcoming"
    ) or "None"

    # Resolve edge target names
    connections_parts = []
    for edge in edges:
        other_id = (
            edge["target_id"] if edge["source_id"] == item_id else edge["source_id"]
        )
        other = journal_ops.get_domain_item(other_id)
        if other:
            connections_parts.append(
                f"- {other['title']} ({edge['relation']}, strength={edge['strength']})"
            )
    connections_text = "\n".join(connections_parts) or "None"

    prompt = CONTEXT_DOC_PROMPT.format(
        title=item["title"],
        item_type=item.get("item_type", "event"),
        domain=item.get("domain", "general"),
        summary=item.get("summary", ""),
        interactions=interactions_text,
        events=events_text,
        connections=connections_text,
    )

    context_doc = _llm.invoke(prompt).content
    embedding = _emb.embed_query(context_doc)

    journal_ops.update_context_doc(item_id, context_doc, embedding)
