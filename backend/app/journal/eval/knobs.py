"""
Tunable parameters for the Journal Graph RAG system.
This is the ONLY file the optimization agent edits.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Knobs:
    # ── Scoring weights ──────────────────────────────
    recency_weight: float = 2.0
    neighbor_weight: float = 1.0
    event_weight: float = 3.0
    freq_weight: float = 0.5

    # ── Decay rates ──────────────────────────────────
    edge_decay_rate: float = 0.03
    event_decay_rate: float = 0.1

    # ── Score floor ──────────────────────────────────
    score_floor_multiplier: float = 0.1

    # ── Entity resolution ────────────────────────────
    rrf_k: int = 60
    entity_resolve_threshold: float = 0.02
    match_count: int = 5

    # ── Graph traversal ──────────────────────────────
    graph_depth: int = 2
    graph_hop_decay: float = 0.8

    # ── Prompts ──────────────────────────────────────
    extract_prompt: str = ""
    context_doc_prompt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


KNOBS = Knobs()
