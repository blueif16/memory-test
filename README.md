# Journal Graph RAG

A temporal knowledge graph system for personal journal entries with autonomous optimization. Extracts entities, tracks relationships over time, and generates intelligent daily briefings.

## What It Does

- **Temporal Entity Tracking**: Extracts people, goals, projects, events from journal entries
- **Decay-Weighted Graph**: Relationships fade over time, keeping briefings relevant
- **Smart Briefings**: Morning summaries of what matters today based on recency, upcoming events, and graph connections
- **Autonomous Optimization**: Self-tuning evaluation loop that improves extraction quality

## Quick Start

### 1. Setup

```bash
# Install dependencies
cd backend
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your Supabase and Gemini API keys

# Run migrations in Supabase SQL Editor
supabase/migrations/20260126_init_gemini_schema.sql
supabase/migrations/20260317_journal_graph_schema.sql
supabase/migrations/20260318_parameterize_scoring.sql
```

### 2. Run the API

```bash
cd backend
python -m app.main
```

### 3. Ingest a Journal Entry

```bash
curl -X POST http://localhost:8000/journal/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "content": "Had coffee with Sarah today. She mentioned her startup launch next week. Need to finish the ML project by Friday.",
    "entry_date": "2026-03-17"
  }'
```

### 4. Get Morning Briefing

```bash
curl -X POST http://localhost:8000/journal/extract \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice"}'
```

## Architecture

### Core Components

- **Ingest Pipeline** (`backend/app/journal/ingest_workflow.py`): LangGraph workflow that extracts entities, resolves them against existing graph, updates relationships
- **Scoring System** (`backend/app/journal/scoring.py`): Ranks entities by recency decay, neighbor activity, upcoming events, mention frequency
- **Context Builder** (`backend/app/journal/context_builder.py`): Generates rich summaries from interaction history for better entity resolution
- **Visualization** (`backend/app/visualization/`): Temporal graph viewer with date slider

### Database Schema

- `domain_items`: Graph nodes (people, goals, projects, places, habits) with lifecycle states
- `edges`: Weighted relationships with time decay
- `upcoming_events`: Future events tied to entities with auto-resolution
- `interactions`: Append-only log of entity mentions
- `graph_snapshots`: Periodic captures for visualization and evaluation
- `diary_entries`: Raw journal content

## Autonomous Optimization

The system includes a Karpathy-style autoresearch loop that tunes parameters to maximize extraction quality.

### How It Works

1. **Frozen Evaluation**: Generates a 30-day synthetic journal scenario once
2. **Experiment Loop**: For each iteration:
   - Commits current parameters to git
   - Runs full scenario with current knobs
   - LLM judge scores each day's briefing (1-5)
   - Computes mean score as the metric
   - LLM planner proposes next parameter change
   - Writes new knobs.py and repeats
3. **Git Tracking**: Each experiment is a commit, best configs are tagged

### Tunable Parameters (`backend/app/journal/eval/knobs.py`)

**Scoring Weights** (how signals combine):
- `recency_weight`: Recent mentions (default: 2.0)
- `neighbor_weight`: Graph neighbor activity (default: 1.0)
- `event_weight`: Upcoming event proximity (default: 3.0)
- `freq_weight`: Total mention frequency (default: 0.5)

**Decay Rates** (how fast signals fade):
- `edge_decay_rate`: Edge/recency decay per day (default: 0.03)
- `event_decay_rate`: Event proximity decay per day (default: 0.1)

**Thresholds**:
- `score_floor_multiplier`: Hide items below median × this (default: 0.1)
- `entity_resolve_threshold`: RRF score to match existing entity (default: 0.02)
- `rrf_k`: RRF fusion constant (default: 60)

**Prompts**:
- `extract_prompt`: Override extraction prompt (empty = default)
- `context_doc_prompt`: Override context doc prompt (empty = default)

### Running Optimization

```bash
cd backend

# Run 10 iterations on college student scenario
python -m app.journal.eval.loop --iterations 10 --archetype college_student --days 30

# Results logged to backend/app/journal/eval/results.tsv
# Best config tagged in git as best-{score}
```

### Monitoring Progress

```bash
# View results
cat backend/app/journal/eval/results.tsv

# Check git history
git log --oneline | grep experiment

# Restore best config
git checkout best-4.200  # or whatever tag
```

### Strategy Guide

The LLM planner follows `backend/app/journal/eval/program.md`:

- Changes ONE parameter per experiment for clear attribution
- Makes moderate changes (25-50% of current value)
- Reviews all prior results before deciding
- Uses failure-pattern-to-fix mappings:
  - Missing deadlines → increase `event_weight`
  - Stale items appearing → increase `edge_decay_rate`
  - Wrong entity matches → adjust `entity_resolve_threshold`
  - Briefing too cluttered → increase `score_floor_multiplier`

## API Endpoints

### Journal Operations

- `POST /journal/ingest`: Save diary entry and extract entities
- `POST /journal/extract`: Generate morning briefing
- `POST /journal/score`: Score all active items
- `GET /journal/graph/{user_id}`: Fetch active items
- `GET /journal/snapshots/{user_id}`: Retrieve snapshots for date range
- `GET /journal/visualize/{user_id}`: Generate temporal graph HTML

### RAG Operations

- `POST /chat`: Self-correcting RAG agent
- `POST /search`: Direct hybrid search
- `POST /ingest`: Ingest content into RAG store

### Evaluation

- `POST /journal/eval/run`: Run full eval loop (dev only)

## Debug Tools

```bash
# Install debug extras
pip install -e ".[debug]"

# Visualize knowledge graph
rag-debug visualize --namespace video_styles --output graph.html

# Debug search query
rag-debug debug "energetic fast cuts" --namespace video_styles

# Run robustness tests
rag-debug test --namespace video_styles
```

See `backend/app/debug/README.md` for full debug toolkit documentation.

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── core/              # Portable RAG module
│   │   │   ├── rag_store.py   # RAGStore class
│   │   │   ├── gemini_embeddings.py
│   │   │   ├── providers.py   # Shared LLM/embeddings
│   │   │   └── adapters.py    # Data extraction
│   │   ├── journal/           # Journal graph system
│   │   │   ├── ingest_workflow.py
│   │   │   ├── context_builder.py
│   │   │   ├── scoring.py
│   │   │   ├── extraction.py
│   │   │   └── eval/          # Optimization loop
│   │   │       ├── loop.py    # Main optimization loop
│   │   │       ├── knobs.py   # Tunable parameters
│   │   │       ├── metric.py  # Scalar score computation
│   │   │       ├── runner.py  # Scenario execution
│   │   │       ├── judge.py   # LLM evaluation
│   │   │       └── program.md # Strategy guide
│   │   ├── graph/             # LangGraph workflow
│   │   ├── services/          # Supabase operations
│   │   ├── visualization/     # Graph rendering
│   │   └── main.py            # FastAPI app
│   └── pyproject.toml
├── supabase/
│   └── migrations/            # SQL schema
├── SPECIFICATION.md           # RAG setup guide for LLMs
└── README.md
```

## Configuration

Environment variables (`.env`):

```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SECRET_KEY=sb_secret_your_key_here
DATABASE_URL=postgresql://postgres:password@db.xxx.supabase.co:5432/postgres

# Gemini API
GEMINI_API_KEY=your-gemini-api-key

# Optional tuning
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIM=768
CHAT_MODEL=gemini-2.0-flash-exp
MATCH_COUNT=5
RRF_K=60
GRAPH_DEPTH=2
```

## Development

```bash
# Run tests
cd backend
pytest

# Start with hot reload
uvicorn app.main:app --reload

# Format code
ruff format .
```

## How the Optimization Loop Works

### Phase 1: Scenario Generation (Once)

```bash
# LLM generates a 30-day synthetic journal for "college_student" archetype
# Each day has:
# - Journal entry text
# - Rubric with expected entities/events to surface
# Cached in backend/app/journal/eval/scenario_cache.json
```

### Phase 2: Experiment Iteration (N times)

```
For iteration i in 1..N:
  1. Load current knobs.py
  2. Git commit: "experiment-{i}: recency_weight=2.5"
  3. Create fresh test user (UUID)
  4. Run 30-day scenario:
     - Each morning: extract briefing with current knobs
     - Each evening: ingest journal entry
  5. LLM judge scores each day's briefing (1-5 scale)
  6. Compute mean score across 30 days
  7. Log to results.tsv
  8. If best score: git tag "best-{score}"
  9. LLM planner reads program.md + results.tsv
  10. Proposes next parameter change
  11. Write new knobs.py
```

### Phase 3: Analysis

```bash
# View all experiments
cat backend/app/journal/eval/results.tsv

# Restore best configuration
git checkout best-4.350

# Or manually edit knobs.py based on insights
```

### What Gets Optimized

The judge evaluates each day's briefing against the rubric:
- **Coverage**: Did it surface expected entities/events?
- **Precision**: Did it avoid stale/irrelevant items?
- **Insight**: Did it make useful connections?

The metric is simply: `mean(judge_scores)` across all 30 days.

### Example Optimization Run

```
Iteration 0: score=3.2 (defaults)
Iteration 1: event_weight=4.0 → score=3.5 (better event coverage)
Iteration 2: edge_decay_rate=0.05 → score=3.8 (fewer stale items)
Iteration 3: score_floor_multiplier=0.15 → score=4.1 (cleaner briefings)
...
Iteration 9: best score=4.3
```

## License

MIT
