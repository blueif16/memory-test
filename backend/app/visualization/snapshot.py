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

    # Get scored items
    scored = journal_ops.score_items(user_id, now_str)

    # Get all active items with full data
    items = journal_ops.get_active_items(user_id)
    items_map = {it["id"]: it for it in items}

    # Merge scores into items
    snapshot_items = []
    for s in scored:
        item_data = items_map.get(s["item_id"], {})
        snapshot_items.append({
            "id": s["item_id"],
            "title": s["title"],
            "domain": s["domain"],
            "item_type": s["item_type"],
            "raw_score": s["raw_score"],
            "above_floor": s["above_floor"],
        })

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
