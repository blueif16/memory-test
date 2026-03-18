# Journal Graph RAG Optimization Program

## Your Goal
Maximize the mean judge score (1-5) across a 30-day journal scenario eval.

## What You Control
Edit `knobs.py` to change one parameter per experiment. The parameters are:

### Scoring Weights (how signals combine into item relevance)
- recency_weight (default 2.0): How much recent mentions matter
- neighbor_weight (default 1.0): How much graph neighbor activity matters
- event_weight (default 3.0): How much upcoming event proximity matters
- freq_weight (default 0.5): How much total mention frequency matters

### Decay Rates (how quickly signals fade)
- edge_decay_rate (default 0.03): Exponential decay per day for edge/recency signals
- event_decay_rate (default 0.1): Exponential decay per day for event proximity

### Thresholds
- score_floor_multiplier (default 0.1): Items below median * this are hidden
- entity_resolve_threshold (default 0.02): RRF score must exceed this to match existing entity
- rrf_k (default 60): RRF fusion constant (higher = more uniform weighting)

### Prompts
- extract_prompt: Override extraction prompt (empty = default)
- context_doc_prompt: Override context doc prompt (empty = default)

## Strategy Guidelines
1. Start with scoring weights -- they have the most direct impact
2. If the judge reports "stale items appearing", try INCREASING edge_decay_rate
3. If the judge reports "missing upcoming events", try INCREASING event_weight
4. If the judge reports "entities not linked", try LOWERING entity_resolve_threshold
5. If the judge reports "too many irrelevant items", try INCREASING score_floor_multiplier
6. Change ONE parameter per experiment for clear attribution
7. Make moderate changes (25-50% of current value), not extreme ones
8. Review all prior results in results.tsv before deciding -- never re-try a failed config
9. After numeric params plateau, try prompt edits

## What the Judge Looks For
- Did the morning briefing surface upcoming events? (problem_if_not_covered)
- Did it avoid showing stale/resolved items? (problem_if_covered)
- Did it include recently discussed entities? (good_if_covered)
- Did it make insightful connections? (best_if_covered)

## Common Failure Patterns → Parameter Fixes
| Failure | Likely Cause | Try |
|---------|-------------|-----|
| Missing upcoming deadlines | event_weight too low | event_weight: 4.0-5.0 |
| Stale items in briefing | edge_decay too slow | edge_decay_rate: 0.05-0.08 |
| Items vanish too fast | edge_decay too fast | edge_decay_rate: 0.01-0.02 |
| Wrong entity matched | resolve threshold too low | entity_resolve_threshold: 0.03-0.05 |
| Duplicate entities | resolve threshold too high | entity_resolve_threshold: 0.01 |
| Briefing too sparse | score_floor too high | score_floor_multiplier: 0.05 |
| Briefing too cluttered | score_floor too low | score_floor_multiplier: 0.2-0.3 |
