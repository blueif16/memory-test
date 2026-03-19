"""
Graph snapshot capture — saves current graph state for visualization + eval.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app.services.journal_ops import journal_ops

logger = logging.getLogger(__name__)


def capture_snapshot(user_id: str, snapshot_date: str | date) -> dict:
    """Capture current graph state into graph_snapshots table.

    Uses temporal filtering so only items created on or before snapshot_date
    are included — this ensures earlier snapshots show fewer nodes.
    """
    if isinstance(snapshot_date, date):
        snapshot_date_str = snapshot_date.isoformat()
    else:
        snapshot_date_str = snapshot_date

    # Build a timestamp for scoring (end of snapshot day)
    now_str = (
        datetime.fromisoformat(snapshot_date_str).isoformat()
        if snapshot_date_str
        else None
    )

    # Get items that existed as of snapshot_date (temporal filtering)
    items = journal_ops.get_active_items_as_of(user_id, snapshot_date_str)
    logger.info(
        "Snapshot %s: found %d active items as of %s",
        user_id[:8], len(items), snapshot_date_str,
    )

    if not items:
        snapshot_data: dict = {"items": [], "edges": [], "events": []}
        journal_ops.save_snapshot(user_id, snapshot_date_str, snapshot_data)
        return snapshot_data

    # Score items — log errors clearly instead of silently falling back
    try:
        scored = journal_ops.score_items(user_id, now_str)
        scored_map = {s["item_id"]: s for s in scored}
        logger.info(
            "Snapshot %s: scoring succeeded, %d items scored (sample scores: %s)",
            user_id[:8],
            len(scored),
            ", ".join(
                f"{s['title'][:20]}={s['raw_score']:.2f}"
                for s in scored[:5]
            ),
        )
    except Exception as e:
        logger.error(
            "Snapshot %s: scoring FAILED — %s. "
            "All scores will be zero. Check that the parameterized "
            "score_domain_items function exists (migration 20260318) "
            "and old 2-param overload is dropped (migration 20260319).",
            user_id[:8], e,
            exc_info=True,
        )
        scored_map = {}

    # Build snapshot items with scores
    active_ids = {item["id"] for item in items}
    snapshot_items = []
    for item in items:
        s = scored_map.get(item["id"], {})
        snapshot_items.append({
            "id": item["id"],
            "title": item["title"],
            "domain": item["domain"],
            "item_type": item["item_type"],
            "raw_score": s.get("raw_score", 0),
            "above_floor": s.get("above_floor", True),
        })

    # Collect edges between active items only
    all_edges = []
    seen_edges: set[str] = set()
    for item in items:
        edges = journal_ops.get_edges_for_item(item["id"])
        for e in edges:
            # Only include edges where both endpoints are in this snapshot
            if (
                e["id"] not in seen_edges
                and e["source_id"] in active_ids
                and e["target_id"] in active_ids
            ):
                seen_edges.add(e["id"])
                all_edges.append({
                    "source_id": e["source_id"],
                    "target_id": e["target_id"],
                    "relation": e["relation"],
                    "strength": e["strength"],
                })

    # Get upcoming events for all items
    all_events = []
    for item in items:
        events = journal_ops.get_events_for_item(item["id"])
        for ev in events:
            if ev.get("status") == "upcoming":
                all_events.append({
                    "id": ev["id"],
                    "domain_item_id": ev["domain_item_id"],
                    "label": ev["label"],
                    "target_date": ev["target_date"],
                    "status": ev["status"],
                })

    snapshot_data = {
        "items": snapshot_items,
        "edges": all_edges,
        "events": all_events,
    }

    logger.info(
        "Snapshot %s on %s: %d items, %d edges, %d events",
        user_id[:8], snapshot_date_str,
        len(snapshot_items), len(all_edges), len(all_events),
    )

    journal_ops.save_snapshot(user_id, snapshot_date_str, snapshot_data)
    return snapshot_data
