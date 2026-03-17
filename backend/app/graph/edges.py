"""
LangGraph Conditional Edges - Decision Logic
=============================================
"""
import logging

from app.graph.state import AgentState
from app.config import config

logger = logging.getLogger(__name__)


def decide_to_generate(state: AgentState) -> str:
    """
    Conditional edge: decide whether to generate or retry.

    Returns:
        "generate" - if context is relevant OR max retries reached
        "rewrite" - if context needs improvement and retries remain
    """
    if state["grade"] == "yes":
        logger.debug("Decision: context relevant, generating")
        return "generate"

    if state["retry_count"] >= config.MAX_RETRY:
        logger.debug(f"Decision: max retries ({config.MAX_RETRY}) reached, generating anyway")
        return "generate"

    logger.debug("Decision: context not relevant, rewriting query")
    return "rewrite"
