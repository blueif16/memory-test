"""
FastAPI App - RAG API
"""
import logging
import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import config

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
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


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        logger.info("-> %s %s [%s]", request.method, request.url.path, request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIdMiddleware)
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


@app.on_event("startup")
async def startup_validation():
    try:
        config.validate()
        logger.info("Configuration validated successfully")
    except EnvironmentError as e:
        logger.error("Startup validation failed: %s", e)
        raise


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
        logger.error("Chat failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/search")
async def search(req: SearchRequest):
    """Direct search."""
    try:
        vec = get_embeddings().embed_query(req.query)
        results = supabase_ops.retrieve_context_mesh(req.query, vec)
        return {"results": results[:req.top_k]}
    except Exception as e:
        logger.error("Search failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/ingest")
async def ingest(req: IngestRequest, bg: BackgroundTasks):
    """Ingest content."""
    try:
        from app.ingestion.extractor import ingest_document
        bg.add_task(ingest_document, req.content, {"source": req.source} if req.source else {})
        return {"status": "queued"}
    except Exception as e:
        logger.error("Ingest failed: %s", e)
        raise HTTPException(500, str(e))


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


class OptimizationRequest(_BM):
    num_iterations: int = 10
    archetype: str = "college_student"
    num_days: int = 30


# In-memory optimization run tracker
_optimization_runs: dict[str, dict] = {}


@app.post("/journal/ingest")
async def journal_ingest(req: JournalIngestRequest, bg: BackgroundTasks):
    """Ingest a journal entry: save diary, extract entities, update graph."""
    try:
        from app.journal.ingest_workflow import run_ingest
        result = run_ingest(req.user_id, req.content, req.entry_date)
        return result
    except Exception as e:
        logger.error("Journal ingest failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/journal/extract")
async def journal_extract(req: JournalExtractRequest):
    """Run scoring + extraction, return plain-text briefing."""
    try:
        from app.journal.extraction import run_extraction
        from datetime import datetime
        now = datetime.fromisoformat(req.date) if req.date else None
        text = run_extraction(req.user_id, now)
        return {"briefing_text": text}
    except Exception as e:
        logger.error("Journal extract failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/journal/score")
async def journal_score(req: JournalScoreRequest):
    """Score all active domain items for a user."""
    try:
        from app.journal.scoring import run_scoring
        items = run_scoring(req.user_id)
        return {"items": items}
    except Exception as e:
        logger.error("Journal score failed: %s", e)
        raise HTTPException(500, str(e))


@app.get("/journal/graph/{user_id}")
async def journal_graph(user_id: str):
    """Get full graph state for a user."""
    try:
        from app.services.journal_ops import journal_ops
        items = journal_ops.get_active_items(user_id)
        return {"items": items}
    except Exception as e:
        logger.error("Journal graph failed: %s", e)
        raise HTTPException(500, str(e))


@app.get("/journal/snapshots/{user_id}")
async def journal_snapshots(
    user_id: str, start_date: str | None = None, end_date: str | None = None
):
    """Get graph snapshots for a date range."""
    try:
        from app.services.journal_ops import journal_ops
        snapshots = journal_ops.get_snapshots(user_id, start_date, end_date)
        return {"snapshots": snapshots}
    except Exception as e:
        logger.error("Journal snapshots failed: %s", e)
        raise HTTPException(500, str(e))


@app.get("/journal/visualize/{user_id}")
async def journal_visualize(
    user_id: str, start_date: str | None = None, end_date: str | None = None
):
    """Generate temporal graph visualization HTML."""
    try:
        from app.visualization.temporal_graph import TemporalGraphVisualizer
        viz = TemporalGraphVisualizer(user_id)
        from datetime import date
        sd = date.fromisoformat(start_date) if start_date else None
        ed = date.fromisoformat(end_date) if end_date else None
        html = viz.render_html(sd, ed)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error("Journal visualize failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/journal/eval/run")
async def journal_eval_run(req: JournalEvalRequest):
    """Run full eval loop (dev only)."""
    try:
        from app.journal.eval.runner import run_eval_loop
        result = run_eval_loop(req.archetype, req.num_days)
        return result
    except Exception as e:
        logger.error("Journal eval failed: %s", e)
        raise HTTPException(500, str(e))


@app.get("/journal/users")
async def journal_users():
    """List all users who have diary entries."""
    try:
        from app.services.journal_ops import journal_ops
        resp = journal_ops.client.table("diary_entries").select("user_id").execute()
        user_ids = sorted(set(row["user_id"] for row in resp.data))
        return {"users": user_ids}
    except Exception as e:
        logger.error("Journal users failed: %s", e)
        raise HTTPException(500, str(e))


@app.post("/journal/eval/optimize")
async def journal_optimize(req: OptimizationRequest, bg: BackgroundTasks):
    """Start optimization loop in background."""
    run_id = str(uuid.uuid4())[:8]
    _optimization_runs[run_id] = {"status": "running", "result": None}

    def _run(rid: str, iters: int, arch: str, days: int):
        try:
            from app.journal.eval.loop import run_optimization_loop
            result = run_optimization_loop(iters, arch, days)
            _optimization_runs[rid] = {"status": "completed", "result": result}
        except Exception as e:
            logger.error("Optimization run %s failed: %s", rid, e)
            _optimization_runs[rid] = {"status": "failed", "result": str(e)}

    bg.add_task(_run, run_id, req.num_iterations, req.archetype, req.num_days)
    return {"run_id": run_id, "status": "started"}


@app.get("/journal/eval/optimize/{run_id}")
async def journal_optimize_status(run_id: str):
    """Poll optimization run status."""
    if run_id not in _optimization_runs:
        raise HTTPException(404, "Run not found")
    return _optimization_runs[run_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
