# Training & Iteration Guidelines

## Autonomous Optimization Loop

This project is a **Journal Graph RAG** system. It uses the **keep/discard** pattern for iterative improvement following the [Karpathy autoresearch](https://github.com/karpathy/autoresearch) pattern.

### The Three Files

| File | Editable? | Role |
|---|---|---|
| `backend/app/journal/eval/*.py` (except `knobs.py`) | **NO** | Frozen eval harness: scenario_generator, judge, runner, aggregator, metric. Never modify. |
| `backend/app/journal/eval/knobs.py` | **YES** | All tunable parameters. The ONLY file you edit for experiments. |
| `backend/app/journal/eval/program.md` | Read-only | Strategy guidelines. Read before every experiment. |

### What You Can Edit in `knobs.py`

These parameters are your knobs — tune them freely:

```python
# Scoring weights (how signals combine into item relevance)
recency_weight: float = 2.0      # How much recent mentions matter
neighbor_weight: float = 1.0     # How much graph neighbor activity matters
event_weight: float = 3.0        # How much upcoming event proximity matters
freq_weight: float = 0.5         # How much total mention frequency matters

# Decay rates (how quickly signals fade)
edge_decay_rate: float = 0.03    # Exponential decay per day for edge/recency
event_decay_rate: float = 0.1    # Exponential decay per day for event proximity

# Thresholds
score_floor_multiplier: float = 0.1   # Items below median * this are hidden
entity_resolve_threshold: float = 0.02 # RRF score must exceed this to match entity
rrf_k: int = 60                        # RRF fusion constant
match_count: int = 5                   # Top-k results

# Graph traversal
graph_depth: int = 2              # Traversal hops
graph_hop_decay: float = 0.8     # Score decay per hop

# Prompts (empty = use default)
extract_prompt: str = ""          # Override extraction prompt
context_doc_prompt: str = ""      # Override context doc prompt
```

### What You Must Never Edit

- `backend/app/journal/eval/scenario_generator.py` — frozen scenario generation
- `backend/app/journal/eval/judge.py` — frozen LLM judge
- `backend/app/journal/eval/runner.py` — frozen day-by-day execution
- `backend/app/journal/eval/metric.py` — frozen scalar metric
- `backend/app/journal/eval/aggregator.py` — frozen diagnosis aggregation
- `backend/app/core/rag_store.py` — core retrieval logic
- `backend/app/journal/ingest_workflow.py` — ingestion pipeline
- `backend/app/journal/extraction.py` — extraction pipeline
- `supabase/migrations/*` — database schema

## The Loop

```
1. Read results.tsv (in backend/app/journal/eval/) to see past experiments
2. Read program.md for strategy guidance
3. Pick ONE parameter change based on history + judge feedback
4. Edit knobs.py with the change
5. git commit -m "exp: [what changed] [why]"
6. Run eval: python -m app.journal.eval.loop --iterations 1 --days 30
7. Record result in results.tsv (auto-appended by the loop)
8. If score improved → keep commit, tag best
9. If worse or crashed → git reset --soft HEAD~1, restore knobs.py
10. Repeat
```

## Metric

The single scalar is **mean judge score** from `compute_metric()`:
- LLM judge scores each day's morning briefing against its rubric (1–5)
- Final metric = mean across all 30 days
- Range: 0.0–5.0. Higher is better.
- **You beat the previous best or you didn't. No partial credit.**

## Test Data

Data is generated automatically by `scenario_generator.py` — 30 days of journal entries + rubrics. Once generated, it's cached at `backend/app/journal/eval/scenario_cache.json`. The same frozen scenario is reused across all experiments so results are comparable.

To pre-generate and inspect:
```bash
cd backend && python -c "
from app.journal.eval.loop import get_or_generate_scenario
import json
s = get_or_generate_scenario('college_student', 30)
print(json.dumps(s, indent=2))
"
```

## Experiment Strategy

### Priority Order (from program.md)
1. **Scoring weights** — most direct impact (recency, event, neighbor, freq)
2. **Decay rates** — if judge reports stale/missing items
3. **Thresholds** — score_floor, entity_resolve
4. **Prompts** — after numeric params plateau

### Failure → Fix Map
| Judge Says | Try |
|---|---|
| Missing upcoming deadlines | event_weight: 4.0–5.0 |
| Stale items in briefing | edge_decay_rate: 0.05–0.08 |
| Items vanish too fast | edge_decay_rate: 0.01–0.02 |
| Wrong entity matched | entity_resolve_threshold: 0.03–0.05 |
| Duplicate entities | entity_resolve_threshold: 0.01 |
| Briefing too sparse | score_floor_multiplier: 0.05 |
| Briefing too cluttered | score_floor_multiplier: 0.2–0.3 |

### Rules
- **One change per experiment.** Never change two parameters at once.
- **Small steps first.** 25–50% changes, not 10x.
- **Log everything.** Even failed experiments are data.
- **Never skip the eval.** No "this should obviously be better."
- **If 3 consecutive experiments fail, revert to last known-good and try a different direction.**
- **Read judge explanations.** The `root_cause` field tells you what to fix next.

## Constraints

- Do not install new packages
- Do not modify the eval harness, judge, runner, or metric
- Do not change Supabase schema or RPC functions
- Do not modify ingestion or extraction pipeline code
- Keep `knobs.py` as a flat dataclass — no conditional logic
- Every experiment must be a clean git commit before eval runs
