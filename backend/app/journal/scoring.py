"""
Pipeline B — Activity Scoring (thin wrapper around SQL function).
"""
from __future__ import annotations

from datetime import datetime

from app.services.journal_ops import journal_ops


def run_scoring(user_id: str, now: datetime | None = None, knobs: dict | None = None) -> list[dict]:
    """Run scoring pipeline. Returns scored items with above_floor flag."""
    now_str = now.isoformat() if now else None
    return journal_ops.score_items(user_id, now_str, knobs=knobs)
