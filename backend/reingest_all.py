"""
Re-ingest all existing diary entries chronologically using the ReAct agent pipeline.

Clears: domain_items, domain_item_interactions, domain_item_edges,
        upcoming_events, graph_snapshots
Keeps:  diary_entries (source of truth)

Then re-runs the ingest pipeline per entry in date order so:
- created_at is set to the actual entry_date
- snapshots grow incrementally day by day

Usage:
    python reingest_all.py [--user <user_id>]
"""
from __future__ import annotations

import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_USER = "00000000-0000-0000-0000-000000000001"


def clear_derived(client, user_id: str):
    logger.info("Clearing derived tables for user %s ...", user_id)

    # Get item ids first for cascade
    items = client.table("domain_items").select("id").eq("user_id", user_id).execute().data
    item_ids = [i["id"] for i in items]

    if item_ids:
        client.table("domain_item_interactions").delete().in_("domain_item_id", item_ids).execute()
        client.table("domain_item_edges").delete().in_("source_id", item_ids).execute()
        client.table("domain_item_edges").delete().in_("target_id", item_ids).execute()
        client.table("upcoming_events").delete().in_("domain_item_id", item_ids).execute()
        client.table("domain_items").delete().eq("user_id", user_id).execute()
        logger.info("  Deleted %d domain items + interactions/edges/events", len(item_ids))
    else:
        logger.info("  No domain items found to delete")

    client.table("graph_snapshots").delete().eq("user_id", user_id).execute()
    logger.info("  Deleted graph_snapshots")


def run(user_id: str):
    from app.services.journal_ops import journal_ops
    from app.journal.ingest_workflow import ingest_app
    from app.visualization.snapshot import capture_snapshot

    client = journal_ops.client

    # Fetch all diary entries ordered by date
    resp = (
        client.table("diary_entries")
        .select("id, content, entry_date")
        .eq("user_id", user_id)
        .order("entry_date")
        .execute()
    )
    entries = resp.data
    logger.info("Found %d diary entries for user %s", len(entries), user_id)
    if not entries:
        logger.warning("No entries found — aborting")
        return

    # Clear derived data
    clear_derived(client, user_id)

    # Group by date (multiple entries same day → ingest separately, snapshot once after last)
    from itertools import groupby
    dates_grouped = {}
    for e in entries:
        dates_grouped.setdefault(e["entry_date"], []).append(e)

    unique_dates = sorted(dates_grouped.keys())
    logger.info("Re-ingesting across %d unique dates: %s", len(unique_dates), unique_dates)

    total_entities = 0
    total_errors = 0
    snapshots_saved = []

    for i, entry_date in enumerate(unique_dates, 1):
        day_entries = dates_grouped[entry_date]
        logger.info("\n=== Day %d/%d: %s (%d entr%s) ===",
                    i, len(unique_dates), entry_date, len(day_entries),
                    "y" if len(day_entries) == 1 else "ies")

        for j, entry in enumerate(day_entries, 1):
            logger.info("  Entry %d/%d (id=%s)", j, len(day_entries), entry["id"])
            t0 = time.perf_counter()

            init_state = {
                "diary_entry": entry["content"],
                "diary_id": entry["id"],
                "user_id": user_id,
                "entry_date": entry_date,
                "extractions": [],
                "processed_count": 0,
                "errors": [],
            }

            try:
                result = ingest_app.invoke(init_state)
                elapsed = time.perf_counter() - t0
                n_entities = result.get("processed_count", 0)
                n_errors = len(result.get("errors", []))
                total_entities += n_entities
                total_errors += n_errors
                logger.info("    Done in %.1fs: %d entities, %d errors",
                            elapsed, n_entities, n_errors)
                if result.get("errors"):
                    for err in result["errors"]:
                        logger.warning("    Error: %s", err)
            except Exception as e:
                logger.error("    FAILED: %s", e, exc_info=True)
                total_errors += 1

        # Capture snapshot once after all entries for this date
        try:
            snapshot = capture_snapshot(user_id, entry_date)
            items_in_snap = len(snapshot.get("items", []))
            nonzero = sum(1 for it in snapshot.get("items", []) if it.get("raw_score", 0) > 0)
            logger.info("  Snapshot saved: %d items (%d with score>0), %d edges",
                        items_in_snap, nonzero, len(snapshot.get("edges", [])))
            snapshots_saved.append({
                "date": entry_date,
                "items": items_in_snap,
                "nonzero_scores": nonzero,
                "edges": len(snapshot.get("edges", [])),
            })
        except Exception as e:
            logger.error("  Snapshot FAILED for %s: %s", entry_date, e)

    # Final summary
    logger.info("\n=== DONE ===")
    logger.info("Total entities processed: %d", total_entities)
    logger.info("Total errors: %d", total_errors)
    logger.info("\nSnapshot growth:")
    for s in snapshots_saved:
        logger.info("  %s: %d items, %d with score>0, %d edges",
                    s["date"], s["items"], s["nonzero_scores"], s["edges"])

    # Verify DB state
    all_items = client.table("domain_items").select("id, title, item_type, created_at") \
        .eq("user_id", user_id).order("created_at").execute().data
    logger.info("\nFinal domain_items in DB (%d):", len(all_items))
    for it in all_items:
        logger.info("  [%s] %r  created=%s", it["item_type"], it["title"], it["created_at"][:10])


if __name__ == "__main__":
    user_id = DEFAULT_USER
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--user" and i + 2 < len(sys.argv):
            user_id = sys.argv[i + 2]
    run(user_id)
