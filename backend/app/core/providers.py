"""
Shared lazy-initialized providers for LLM and embeddings.
Ensures a single instance across the application, created on first use.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import config


@lru_cache(maxsize=1)
def get_llm():
    """Shared ChatGoogleGenerativeAI instance."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=config.CHAT_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0,
    )


@lru_cache(maxsize=1)
def get_embeddings():
    """Shared GeminiEmbeddings instance."""
    from app.core.gemini_embeddings import GeminiEmbeddings
    return GeminiEmbeddings(
        model=config.EMBEDDING_MODEL,
        output_dimensionality=config.EMBEDDING_DIM,
    )
