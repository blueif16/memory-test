"""
Journal Graph Operations — DB service layer for domain items, edges,
interactions, events, diary entries, scoring, and snapshots.
"""
from __future__ import annotations

from datetime import date, datetime

from supabase import create_client, Client
from app.config import config


class JournalOps:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # ── Domain Items ────────────────────────────────────────────

    def create_domain_item(
        self,
        user_id: str,
        title: str,
        domain: str,
        item_type: str = "event",
        summary: str = "",
    ) -> dict:
        resp = self.client.table("domain_items").insert({
            "user_id": user_id,
            "title": title,
            "domain": domain,
            "item_type": item_type,
            "summary": summary,
        }).execute()
        return resp.data[0]

    def get_domain_item(self, item_id: str) -> dict | None:
        resp = (
            self.client.table("domain_items")
            .select("*")
            .eq("id", item_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def update_lifecycle(
        self, item_id: str, status: str, resolution_note: str | None = None
    ) -> dict:
        payload: dict = {
            "lifecycle_status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if status in ("completed", "abandoned"):
            payload["resolved_at"] = datetime.utcnow().isoformat()
        if resolution_note:
            payload["resolution_note"] = resolution_note
        resp = (
            self.client.table("domain_items")
            .update(payload)
            .eq("id", item_id)
            .execute()
        )
        return resp.data[0]

    def get_stale_items(self, user_id: str) -> list[dict]:
        resp = (
            self.client.table("domain_items")
            .select("*")
            .eq("user_id", user_id)
            .eq("context_doc_stale", True)
            .eq("lifecycle_status", "active")
            .execute()
        )
        return resp.data

    def update_context_doc(
        self, item_id: str, context_doc: str, embedding: list[float]
    ) -> dict:
        resp = (
            self.client.table("domain_items")
            .update({
                "context_doc": context_doc,
                "summary_embedding": embedding,
                "context_doc_stale": False,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", item_id)
            .execute()
        )
        return resp.data[0]

    def get_active_items(self, user_id: str) -> list[dict]:
        resp = (
            self.client.table("domain_items")
            .select("id, title, domain, item_type, summary")
            .eq("user_id", user_id)
            .eq("lifecycle_status", "active")
            .execute()
        )
        return resp.data

    # ── Entity Resolution (SQL RPC) ────────────────────────────

    def resolve_entity(
        self,
        query_text: str,
        query_embedding: list[float],
        user_id: str,
        match_count: int = 5,
    ) -> list[dict]:
        resp = self.client.rpc("resolve_domain_item", {
            "query_text": query_text,
            "query_embedding": query_embedding,
            "p_user_id": user_id,
            "match_count": match_count,
        }).execute()
        return resp.data

    # ── Edges ───────────────────────────────────────────────────

    def upsert_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        strength_delta: float = 1.0,
    ) -> dict:
        resp = (
            self.client.table("domain_item_edges")
            .upsert(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": relation,
                    "strength": strength_delta,
                    "last_reinforced_at": datetime.utcnow().isoformat(),
                },
                on_conflict="source_id,target_id,relation",
            )
            .execute()
        )
        return resp.data[0]

    def reinforce_edge(self, source_id: str, target_id: str, relation: str) -> dict:
        # Fetch current, then increment
        resp = (
            self.client.table("domain_item_edges")
            .select("id, strength")
            .eq("source_id", source_id)
            .eq("target_id", target_id)
            .eq("relation", relation)
            .limit(1)
            .execute()
        )
        if resp.data:
            edge = resp.data[0]
            update_resp = (
                self.client.table("domain_item_edges")
                .update({
                    "strength": edge["strength"] + 1,
                    "last_reinforced_at": datetime.utcnow().isoformat(),
                })
                .eq("id", edge["id"])
                .execute()
            )
            return update_resp.data[0]
        # Edge doesn't exist yet — create it
        return self.upsert_edge(source_id, target_id, relation)

    # ── Interactions ────────────────────────────────────────────

    def add_interaction(
        self,
        domain_item_id: str,
        diary_id: str,
        snippet: str,
        noted_at: str | None = None,
    ) -> dict:
        payload = {
            "domain_item_id": domain_item_id,
            "diary_id": diary_id,
            "snippet": snippet,
        }
        if noted_at:
            payload["noted_at"] = noted_at
        resp = self.client.table("domain_item_interactions").insert(payload).execute()
        return resp.data[0]

    def get_interactions(self, domain_item_id: str, limit: int = 10) -> list[dict]:
        resp = (
            self.client.table("domain_item_interactions")
            .select("*")
            .eq("domain_item_id", domain_item_id)
            .order("noted_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data

    # ── Upcoming Events ─────────────────────────────────────────

    def add_upcoming_event(
        self,
        domain_item_id: str,
        label: str,
        target_date: str,
        detail: str = "",
        source_diary_id: str | None = None,
    ) -> dict:
        payload = {
            "domain_item_id": domain_item_id,
            "label": label,
            "target_date": target_date,
            "detail": detail,
        }
        if source_diary_id:
            payload["source_diary_id"] = source_diary_id
        resp = self.client.table("upcoming_events").insert(payload).execute()
        return resp.data[0]

    def auto_resolve_events(self, before_date: str) -> int:
        resp = (
            self.client.table("upcoming_events")
            .update({"status": "completed"})
            .eq("status", "upcoming")
            .lt("target_date", before_date)
            .execute()
        )
        return len(resp.data)

    def get_upcoming_events(
        self, user_id: str, status: str = "upcoming"
    ) -> list[dict]:
        resp = (
            self.client.table("upcoming_events")
            .select("*, domain_items!inner(user_id)")
            .eq("domain_items.user_id", user_id)
            .eq("status", status)
            .order("target_date")
            .execute()
        )
        return resp.data

    # ── Diary Entries ───────────────────────────────────────────

    def save_diary_entry(self, user_id: str, content: str, entry_date: str) -> dict:
        resp = self.client.table("diary_entries").insert({
            "user_id": user_id,
            "content": content,
            "entry_date": entry_date,
        }).execute()
        return resp.data[0]

    def get_diary_entry(self, diary_id: str) -> dict | None:
        resp = (
            self.client.table("diary_entries")
            .select("*")
            .eq("id", diary_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    # ── Scoring + Extraction (SQL RPC) ──────────────────────────

    def score_items(self, user_id: str, now: str | None = None) -> list[dict]:
        params: dict = {"p_user_id": user_id}
        if now:
            params["p_now"] = now
        resp = self.client.rpc("score_domain_items", params).execute()
        return resp.data

    def extract_briefing_data(self, user_id: str, now: str | None = None) -> list[dict]:
        params: dict = {"p_user_id": user_id}
        if now:
            params["p_now"] = now
        resp = self.client.rpc("extract_briefing_data", params).execute()
        return resp.data

    # ── Snapshots ───────────────────────────────────────────────

    def save_snapshot(self, user_id: str, snapshot_date: str, data: dict) -> dict:
        resp = (
            self.client.table("graph_snapshots")
            .upsert(
                {
                    "user_id": user_id,
                    "snapshot_date": snapshot_date,
                    "snapshot_data": data,
                },
                on_conflict="user_id,snapshot_date",
            )
            .execute()
        )
        return resp.data[0]

    def get_snapshots(
        self,
        user_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        q = (
            self.client.table("graph_snapshots")
            .select("*")
            .eq("user_id", user_id)
            .order("snapshot_date")
        )
        if start_date:
            q = q.gte("snapshot_date", start_date)
        if end_date:
            q = q.lte("snapshot_date", end_date)
        return q.execute().data

    # ── Recently Completed ──────────────────────────────────────

    def get_recently_completed(self, user_id: str, days: int = 7) -> list[dict]:
        cutoff = datetime.utcnow().isoformat()
        resp = (
            self.client.table("domain_items")
            .select("id, title, domain, item_type, resolved_at, resolution_note")
            .eq("user_id", user_id)
            .in_("lifecycle_status", ["completed", "abandoned"])
            .order("resolved_at", desc=True)
            .limit(20)
            .execute()
        )
        # Filter in Python for the days window
        from datetime import timedelta
        cutoff_dt = datetime.utcnow() - timedelta(days=days)
        return [
            r for r in resp.data
            if r.get("resolved_at") and r["resolved_at"] >= cutoff_dt.isoformat()
        ]

    # ── Graph Edges for an item ─────────────────────────────────

    def get_edges_for_item(self, item_id: str) -> list[dict]:
        resp_source = (
            self.client.table("domain_item_edges")
            .select("*")
            .eq("source_id", item_id)
            .execute()
        )
        resp_target = (
            self.client.table("domain_item_edges")
            .select("*")
            .eq("target_id", item_id)
            .execute()
        )
        return resp_source.data + resp_target.data

    def get_events_for_item(self, item_id: str) -> list[dict]:
        resp = (
            self.client.table("upcoming_events")
            .select("*")
            .eq("domain_item_id", item_id)
            .order("target_date")
            .execute()
        )
        return resp.data


journal_ops = JournalOps()
