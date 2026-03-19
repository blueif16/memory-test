"""
Graph snapshot capture — saves current graph state for visualization + eval.
"""
from __future__ import annotations

from datetime import date, datetime

from app.services.journal_ops import journal_ops


def capture_snapshot(user_id: str, snapshot_date: str | date) -> dict:
    """Capture current graph state into graph_snapshots table."""
    if isinstance(snapshot_date, date):
        snapshot_date_str = snapshot_date.isoformat()
    else:
        snapshot_date_str = snapshot_date

    now_str = datetime.fromisoformat(snapshot_date_str).isoformat() if snapshot_date_str else None

    # Get all active items with full data
    items = journal_ops.get_active_items(user_id)

    # Try scoring, but skip if DB function fails
    try:
        scored = journal_ops.score_items(user_id, now_str)
        scored_map = {s["item_id"]: s for s in scored}
        # Merge scores into items
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
    except Exception as e:
        # Fallback: just use items without scores
        snapshot_items = [
            {
                "id": item["id"],
                "title": item["title"],
                "domain": item["domain"],
                "item_type": item["item_type"],
                "raw_score": 0,
                "above_floor": True,
            }
            for item in items
        ]

    # Collect all edges between active items
    all_edges = []
    seen_edges = set()
    for item in items:
        edges = journal_ops.get_edges_for_item(item["id"])
        for e in edges:
            if e["id"] not in seen_edges:
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

    journal_ops.save_snapshot(user_id, snapshot_date_str, snapshot_data)
    return snapshot_data
