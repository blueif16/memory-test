# Training & Iteration Guidelines

## Autonomous Optimization Loop

This project uses the **keep/discard** pattern for iterative improvement. Follow these rules exactly.

### The Three Files

| File | Editable? | Role |
|---|---|---|
| `backend/app/debug/evaluator.py` | **NO** | Frozen eval harness. Never modify. |
| `backend/app/config.py` | **YES** | All tunable parameters. Only file you edit for experiments. |
| `CLAUDE.md` | Read-only | Your instructions. Follow them. |

### What You Can Edit in `config.py`

These parameters are your knobs — tune them freely:

```python
EMBEDDING_MODEL   # e.g. "gemini-embedding-001" — try different models
EMBEDDING_DIM     # Must match model output (768 for gemini-embedding-001)
MATCH_COUNT       # Top-k results returned (default: 5, try 3–10)
RRF_K             # RRF smoothing constant (default: 60, try 20–100)
GRAPH_DEPTH       # Graph traversal hops (default: 2, try 1–3)
ENTITY_RESOLVE_THRESHOLD  # Entity dedup threshold (default: 0.02)
EDGE_DECAY_RATE           # Graph edge weight decay (default: 0.03)
SCORE_FLOOR_MULTIPLIER    # Minimum score floor (default: 0.1)
```

### What You Must Never Edit

- `backend/app/debug/evaluator.py` — frozen eval harness
- `backend/app/core/rag_store.py` — core retrieval logic
- `supabase/migrations/*` — database schema
- Any search function signatures or return formats

## The Loop

```
1. Read results.tsv (if exists) to see past experiments
2. Pick ONE parameter change based on history
3. Edit config.py with the change
4. git commit -m "exp: [what changed] [why]"
5. Run eval: python -m app.debug.evaluator
6. Record result in results.tsv: commit_hash | metric | status | description
7. If overall_score improved → keep commit, update best_score
8. If worse or crashed → git reset --soft HEAD~1, restore config.py
9. Repeat
```

## Metric

The single scalar is `overall_score` from `RAGEvaluator._compute_aggregate()`:
- Weighted average of: context_precision, context_recall, faithfulness, answer_relevancy
- Range: 0.0–1.0. Higher is better.
- **You beat the previous best or you didn't. No partial credit.**

## Experiment Strategy

### Priority Order
1. `MATCH_COUNT` — most direct impact on recall vs precision tradeoff
2. `RRF_K` — controls how vector and BM25 scores blend
3. `GRAPH_DEPTH` — deeper = more context but more noise
4. `EMBEDDING_MODEL` — biggest potential gain, highest risk
5. `ENTITY_RESOLVE_THRESHOLD` / `EDGE_DECAY_RATE` — fine-tuning only after basics are solid

### Rules
- **One change per experiment.** Never change two parameters at once.
- **Small steps first.** Before trying MATCH_COUNT=20, try MATCH_COUNT=6.
- **Log everything.** Even failed experiments are data.
- **Never skip the eval.** No "this should obviously be better."
- **If 3 consecutive experiments fail, revert to last known-good and try a different direction.**

## results.tsv Format

```tsv
timestamp	commit	param_changed	old_value	new_value	overall_score	status	notes
2026-03-18T10:00:00	abc123f	MATCH_COUNT	5	7	0.72	kept	recall improved without precision loss
2026-03-18T10:15:00	def456a	RRF_K	60	40	0.68	discarded	precision dropped significantly
```

Create this file if it doesn't exist. Append only — never delete rows.

## Monitoring Best Practices

- Track the **trend** across experiments, not just the last result
- Watch for precision/recall tradeoffs: if one metric jumps but another drops, the overall_score catches it
- If overall_score plateaus for 5+ experiments, shift to a different parameter
- Compare against the baseline (first committed config) periodically

## Constraints

- Do not install new packages
- Do not modify the eval harness or test cases
- Do not change Supabase schema or RPC functions
- Do not modify `rag_store.py` search logic
- Keep `config.py` as flat top-level constants — no conditional logic, no imports beyond `os` and `dotenv`
- Every experiment must be a clean git commit before eval runs
