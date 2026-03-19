"""
Regenerate graph snapshots from existing diary entries.

Iterates through all diary entries chronologically and re-captures a snapshot
for each entry date, so snapshots correctly reflect incremental graph growth
with proper temporal filtering and scoring.

Usage:
    python -m app.visualization.regenerate_snapshots <user_id>
"""
from __future__ import annotations

import logging
import sys

from app.services.journal_ops import journal_ops
from app.visualization.snapshot import capture_snapshot

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def regenerate_snapshots(user_id: str) -> list[dict]:
    """Delete existing snapshots and rebuild from diary entry dates."""
    # Get all diary entries for the user, ordered by date
    resp = (
        journal_ops.client.table("diary_entries")
        .select("entry_date")
        .eq("user_id", user_id)
        .order("entry_date")
        .execute()
    )
    entries = resp.data
    if not entries:
        logger.warning("No diary entries found for user %s", user_id)
        return []

    # Get unique dates (there may be multiple entries per day)
    dates = sorted(set(e["entry_date"] for e in entries))
    logger.info(
        "Found %d diary entries across %d unique dates for user %s",
        len(entries), len(dates), user_id,
    )

    results = []
    for i, entry_date in enumerate(dates, 1):
        logger.info("--- Regenerating snapshot %d/%d: %s ---", i, len(dates), entry_date)
        try:
            snapshot = capture_snapshot(user_id, entry_date)
            items = snapshot.get("items", [])
            edges = snapshot.get("edges", [])
            nonzero_scores = sum(1 for it in items if it.get("raw_score", 0) > 0)
            logger.info(
                "  Result: %d items (%d with score > 0), %d edges",
                len(items), nonzero_scores, len(edges),
            )
            results.append({"date": entry_date, "snapshot": snapshot})
        except Exception as e:
            logger.error("  FAILED for %s: %s", entry_date, e, exc_info=True)
            results.append({"date": entry_date, "error": str(e)})

    logger.info(
        "Regeneration complete: %d snapshots processed", len(results),
    )
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.visualization.regenerate_snapshots <user_id>")
        sys.exit(1)

    user_id = sys.argv[1]
    regenerate_snapshots(user_id)
