"""
Real integration test — hits actual Supabase + Gemini.
Runs two diary entries for a fresh test user and verifies nodes accumulate correctly.
Delete test data after with: python test_integration.py --cleanup
"""
from __future__ import annotations
import sys
import uuid
import time

TEST_USER = "00000000-0000-0000-0000-000000000099"  # throwaway test user

ENTRY_1_DATE = "2026-03-10"
ENTRY_1 = """
Had a long meeting with Sarah about the ML Project today. She thinks we can finish
the model training by next Friday. Also started reading the Deep Learning book for my
CS coursework. Need to submit the project proposal by March 15.
"""

ENTRY_2_DATE = "2026-03-12"
ENTRY_2 = """
Caught up with Sarah again over coffee. The ML Project is going well — we ran the first
training run successfully. Deep Learning book chapter 3 was really dense. Also joined
the gym today, planning to go every morning.
"""


def cleanup(ops, user_id: str):
    c = ops.client
    # Delete in dependency order
    items = c.table("domain_items").select("id").eq("user_id", user_id).execute().data
    item_ids = [i["id"] for i in items]
    if item_ids:
        c.table("domain_item_interactions").delete().in_("domain_item_id", item_ids).execute()
        c.table("domain_item_edges").delete().in_("source_id", item_ids).execute()
        c.table("domain_item_edges").delete().in_("target_id", item_ids).execute()
        c.table("upcoming_events").delete().in_("domain_item_id", item_ids).execute()
        c.table("domain_items").delete().eq("user_id", user_id).execute()
    c.table("diary_entries").delete().eq("user_id", user_id).execute()
    c.table("graph_snapshots").delete().eq("user_id", user_id).execute()
    print(f"Cleaned up all data for user {user_id}")


def run():
    from app.services.journal_ops import journal_ops
    from app.journal.ingest_workflow import run_ingest

    if "--cleanup" in sys.argv:
        cleanup(journal_ops, TEST_USER)
        return

    print(f"\n=== Integration Test — user {TEST_USER} ===")
    print("\n--- Pre-cleanup ---")
    cleanup(journal_ops, TEST_USER)

    # ── Entry 1 ─────────────────────────────────────────────────
    print(f"\n--- Ingesting Entry 1 ({ENTRY_1_DATE}) ---")
    t0 = time.perf_counter()
    r1 = run_ingest(TEST_USER, ENTRY_1, ENTRY_1_DATE)
    print(f"Done in {time.perf_counter()-t0:.1f}s")
    print(f"  diary_id      : {r1['diary_id']}")
    print(f"  entities_found: {r1['entities_found']}")
    print(f"  processed     : {r1['processed_count']}")
    print(f"  errors        : {r1['errors']}")

    items_after_1 = journal_ops.client.table("domain_items") \
        .select("id, title, item_type, domain, created_at") \
        .eq("user_id", TEST_USER).execute().data
    print(f"\n  Nodes in DB after entry 1 ({len(items_after_1)}):")
    for it in items_after_1:
        print(f"    [{it['item_type']:8}] {it['title']!r:40} created={it['created_at'][:10]}")

    assert len(items_after_1) > 0, "FAIL: no nodes created after entry 1"
    assert all(it['created_at'][:10] == ENTRY_1_DATE for it in items_after_1), \
        "FAIL: created_at not set to entry_date"
    print("  PASS: nodes created with correct created_at")

    node_titles_1 = {it['title'].lower() for it in items_after_1}

    # ── Entry 2 ─────────────────────────────────────────────────
    print(f"\n--- Ingesting Entry 2 ({ENTRY_2_DATE}) ---")
    t0 = time.perf_counter()
    r2 = run_ingest(TEST_USER, ENTRY_2, ENTRY_2_DATE)
    print(f"Done in {time.perf_counter()-t0:.1f}s")
    print(f"  diary_id      : {r2['diary_id']}")
    print(f"  entities_found: {r2['entities_found']}")
    print(f"  processed     : {r2['processed_count']}")
    print(f"  errors        : {r2['errors']}")

    items_after_2 = journal_ops.client.table("domain_items") \
        .select("id, title, item_type, domain, created_at") \
        .eq("user_id", TEST_USER).execute().data
    print(f"\n  Nodes in DB after entry 2 ({len(items_after_2)}):")
    for it in items_after_2:
        print(f"    [{it['item_type']:8}] {it['title']!r:40} created={it['created_at'][:10]}")

    # Key assertion: Sarah and ML Project should NOT have doubled
    titles_after_2 = [it['title'].lower() for it in items_after_2]
    sarah_count = sum(1 for t in titles_after_2 if 'sarah' in t)
    ml_count = sum(1 for t in titles_after_2 if 'ml' in t or 'machine learning' in t)
    print(f"\n  'Sarah' nodes: {sarah_count} (expect 1)")
    print(f"  'ML Project' nodes: {ml_count} (expect 1)")

    assert sarah_count == 1, f"FAIL: Sarah duplicated — {sarah_count} nodes"
    assert ml_count == 1, f"FAIL: ML Project duplicated — {ml_count} nodes"
    print("  PASS: recurring entities merged, not duplicated")

    # Gym should be new (only in entry 2)
    gym_count = sum(1 for t in titles_after_2 if 'gym' in t)
    print(f"  'gym' nodes: {gym_count} (expect 1)")
    assert gym_count >= 1, "FAIL: gym not created from entry 2"
    print("  PASS: new entity from entry 2 was created")

    # Check interactions — Sarah should have 2
    sarah_node = next(it for it in items_after_2 if 'sarah' in it['title'].lower())
    interactions = journal_ops.get_interactions(sarah_node['id'], limit=10)
    print(f"\n  Sarah interactions: {len(interactions)} (expect 2)")
    assert len(interactions) == 2, f"FAIL: Sarah should have 2 interactions, got {len(interactions)}"
    print("  PASS: Sarah has 2 interactions across 2 entries")

    print("\n=== ALL TESTS PASSED ===")
    print(f"\nTo clean up: python test_integration.py --cleanup")


if __name__ == "__main__":
    run()
