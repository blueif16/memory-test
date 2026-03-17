"""
Graph Extractor - Extract relations from content
================================================

Uses LLM to find relationships between content pieces.
"""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from app.services.supabase_ops import supabase_ops
from app.core.providers import get_llm, get_embeddings

logger = logging.getLogger(__name__)


class Edge(BaseModel):
    target_snippet: str = Field(description="Quote from text that relates")
    relation: str = Field(description="relates_to, contradicts, contains, requires")


class Extraction(BaseModel):
    edges: List[Edge]


def ingest_document(content: str, metadata: dict | None = None) -> dict:
    """Ingest with optional graph extraction."""
    # Embed and insert
    vec = get_embeddings().embed_query(content)
    node = supabase_ops.insert_document(content, vec, metadata or {})
    source_id = node["id"]
    
    # Try to extract relations
    edges_created = 0
    errors = []
    try:
        extractor = get_llm().with_structured_output(Extraction)
        result = extractor.invoke(f"Extract key relationships from:\n{content[:3000]}")

        for edge in result.edges:
            target = supabase_ops.find_document_by_content(edge.target_snippet[:100])
            if target and target["id"] != source_id:
                try:
                    supabase_ops.insert_relation(source_id, target["id"], edge.relation, {})
                    edges_created += 1
                except Exception as e:
                    logger.warning(f"Edge insertion failed for '{edge.target_snippet[:50]}': {e}")
                    errors.append(f"edge_insert: {e}")
    except Exception as e:
        logger.error(f"Graph extraction failed: {e}")
        errors.append(f"extraction: {e}")

    return {"id": source_id, "edges": edges_created, "errors": errors}
