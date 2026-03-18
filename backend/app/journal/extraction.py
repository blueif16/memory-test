"""
Pipeline C — Daily Extraction (read path).
Produces a plain-text briefing from scored graph data.
"""
from __future__ import annotations

from datetime import datetime
from collections import defaultdict

from app.services.journal_ops import journal_ops


def run_extraction(user_id: str, now: datetime | None = None, knobs: dict | None = None) -> str:
    """Produce plain-text briefing for fortune-telling prompt."""
    now = now or datetime.utcnow()
    now_str = now.isoformat()

    data = journal_ops.extract_briefing_data(user_id, now_str, knobs=knobs)
    completed = journal_ops.get_recently_completed(user_id, days=7)

    return format_briefing(data, completed, now)


def format_briefing(
    items: list[dict], completed: list[dict], now: datetime
) -> str:
    """Format extraction data into plain text block."""
    weekday = now.strftime("%A")
    date_str = now.strftime("%Y-%m-%d")
    lines = [f"Today is {date_str}, {weekday}.", ""]

    # Group by domain
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_domain[item["domain"]].append(item)

    for domain in sorted(by_domain.keys()):
        lines.append(f"## {domain}")
        for item in by_domain[domain]:
            # Title line
            title = item["title"]
            item_type = item.get("item_type", "event")
            summary = item.get("summary", "")
            lines.append(f"{title} ({item_type}) — {summary}")

            # Upcoming events
            events = item.get("upcoming_events_json", [])
            if isinstance(events, list):
                for ev in events:
                    label = ev.get("label", "")
                    target = ev.get("target_date", "")
                    detail = ev.get("detail", "")
                    detail_str = f" — {detail}" if detail else ""
                    lines.append(f"  Upcoming: {label} ({target}){detail_str}")

            # Recent snippets
            snippets = item.get("recent_snippets_json", [])
            if isinstance(snippets, list):
                for sn in snippets:
                    snippet_text = sn.get("snippet", "")
                    noted = sn.get("noted_at", "")
                    if noted:
                        noted = noted[:10]  # Just the date part
                    lines.append(f'  Recent: "{snippet_text}" ({noted})')

            # Connections
            connections = item.get("connections_json", [])
            if isinstance(connections, list) and connections:
                conn_strs = [c.get("title", "") for c in connections if c.get("title")]
                if conn_strs:
                    lines.append(f"  Connections: {', '.join(conn_strs)}")

            lines.append("")

    # Recently completed section
    if completed:
        lines.append("RECENTLY COMPLETED (last 7 days):")
        for item in completed:
            resolved = item.get("resolved_at", "")[:10] if item.get("resolved_at") else ""
            note = item.get("resolution_note", "")
            note_str = f': "{note}"' if note else ""
            lines.append(
                f"{item['title']} ({item.get('item_type', 'event')}) — "
                f"{item.get('lifecycle_status', 'completed')} {resolved}{note_str}"
            )

    return "\n".join(lines)
