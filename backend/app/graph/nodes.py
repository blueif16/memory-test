"""
LangGraph Nodes - Self-Correcting RAG
=====================================

Retrieve → Grade → (Rewrite if needed) → Generate
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from app.config import config
from app.graph.state import AgentState

if TYPE_CHECKING:
    from app.core import RAGStore


def create_nodes(rag: "RAGStore", llm: ChatGoogleGenerativeAI | None = None) -> dict[str, Callable]:
    """
    Create workflow nodes bound to a RAGStore.

    Returns dict with: retrieve, grade, rewrite, generate
    """
    _llm = llm or ChatGoogleGenerativeAI(model=config.CHAT_MODEL, temperature=0)

    def retrieve(state: AgentState) -> dict:
        """Search knowledge base."""
        results = rag.search(state["question"])
        context = "\n\n".join([r.get("content", "") for r in results])
        return {"context": context, "retry_count": state.get("retry_count", 0)}

    def grade(state: AgentState) -> dict:
        """Check if context answers the question."""
        prompt = f"""Does this context help answer the question? Reply only 'yes' or 'no'.

Context: {state['context'][:2000]}

Question: {state['question']}"""

        response = _llm.invoke([HumanMessage(content=prompt)])
        return {"grade": "yes" if "yes" in response.content.lower() else "no"}

    def rewrite(state: AgentState) -> dict:
        """Rewrite query for better retrieval."""
        prompt = f"Rewrite this query to find better results: {state['question']}"
        response = _llm.invoke([HumanMessage(content=prompt)])
        return {"question": response.content.strip(), "retry_count": state["retry_count"] + 1}

    def generate(state: AgentState) -> dict:
        """Generate answer from context."""
        prompt = f"""Answer based on this context. If context doesn't help, say so.

Context:
{state['context']}

Question: {state['question']}"""

        response = _llm.invoke([HumanMessage(content=prompt)])
        return {"messages": [response]}

    return {
        "retrieve": retrieve,
        "grade": grade,
        "rewrite": rewrite,
        "generate": generate
    }
