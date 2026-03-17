"""
FastAPI App - RAG API
"""
import logging

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import config

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str
    conversation_id: str = "default"
    user_id: str = ""


class IngestRequest(BaseModel):
    content: str
    source: str | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


app = FastAPI(title="RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default workflow
from app.graph.workflow import app as agent_app, checkpointer
from app.services.supabase_ops import supabase_ops
from app.core.providers import get_embeddings


@app.post("/chat")
async def chat(req: ChatRequest):
    """Self-correcting RAG agent."""
    try:
        result = agent_app.invoke(
            {"question": req.query, "user_id": req.user_id},
            config={"configurable": {"thread_id": req.conversation_id}}
        )
        return {
            "response": result["messages"][-1].content if result.get("messages") else "",
            "retries": result.get("retry_count", 0)
        }
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(500, str(e))


@app.post("/search")
async def search(req: SearchRequest):
    """Direct search."""
    vec = get_embeddings().embed_query(req.query)
    results = supabase_ops.retrieve_context_mesh(req.query, vec)
    return {"results": results[:req.top_k]}


@app.post("/ingest")
async def ingest(req: IngestRequest, bg: BackgroundTasks):
    """Ingest content."""
    from app.ingestion.extractor import ingest_document
    bg.add_task(ingest_document, req.content, {"source": req.source} if req.source else {})
    return {"status": "queued"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "persistence": checkpointer is not None,
    }


# ── Journal Graph RAG Endpoints ─────────────────────────────────

from pydantic import BaseModel as _BM


class JournalIngestRequest(_BM):
    user_id: str
    content: str
    entry_date: str  # YYYY-MM-DD


class JournalExtractRequest(_BM):
    user_id: str
    date: str | None = None


class JournalScoreRequest(_BM):
    user_id: str


class JournalEvalRequest(_BM):
    archetype: str = "college_student"
    num_days: int = 30


@app.post("/journal/ingest")
async def journal_ingest(req: JournalIngestRequest, bg: BackgroundTasks):
    """Ingest a journal entry: save diary, extract entities, update graph."""
    from app.journal.ingest_workflow import run_ingest
    result = run_ingest(req.user_id, req.content, req.entry_date)
    return result


@app.post("/journal/extract")
async def journal_extract(req: JournalExtractRequest):
    """Run scoring + extraction, return plain-text briefing."""
    from app.journal.extraction import run_extraction
    from datetime import datetime
    now = datetime.fromisoformat(req.date) if req.date else None
    text = run_extraction(req.user_id, now)
    return {"briefing_text": text}


@app.post("/journal/score")
async def journal_score(req: JournalScoreRequest):
    """Score all active domain items for a user."""
    from app.journal.scoring import run_scoring
    items = run_scoring(req.user_id)
    return {"items": items}


@app.get("/journal/graph/{user_id}")
async def journal_graph(user_id: str):
    """Get full graph state for a user."""
    from app.services.journal_ops import journal_ops
    items = journal_ops.get_active_items(user_id)
    return {"items": items}


@app.get("/journal/snapshots/{user_id}")
async def journal_snapshots(
    user_id: str, start_date: str | None = None, end_date: str | None = None
):
    """Get graph snapshots for a date range."""
    from app.services.journal_ops import journal_ops
    snapshots = journal_ops.get_snapshots(user_id, start_date, end_date)
    return {"snapshots": snapshots}


@app.get("/journal/visualize/{user_id}")
async def journal_visualize(
    user_id: str, start_date: str | None = None, end_date: str | None = None
):
    """Generate temporal graph visualization HTML."""
    from app.visualization.temporal_graph import TemporalGraphVisualizer
    viz = TemporalGraphVisualizer(user_id)
    from datetime import date
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    html = viz.render_html(sd, ed)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@app.post("/journal/eval/run")
async def journal_eval_run(req: JournalEvalRequest):
    """Run full eval loop (dev only)."""
    from app.journal.eval.runner import run_eval_loop
    result = run_eval_loop(req.archetype, req.num_days)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
