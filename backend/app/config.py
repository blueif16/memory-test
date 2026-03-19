import logging
import os
from dotenv import load_dotenv, find_dotenv

# 从当前工作目录开始向上搜索 .env 文件
# 这样无论从哪里执行，都能找到项目根目录的 .env
load_dotenv(find_dotenv(usecwd=True))

_logger = logging.getLogger(__name__)


def _safe_int(val: str | None, default: int) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        _logger.warning("Invalid int value %r, using default %d", val, default)
        return default


def _safe_float(val: str | None, default: float) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        _logger.warning("Invalid float value %r, using default %s", val, default)
        return default


class Config:
    """统一配置管理"""

    # Debug mode
    DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

    # Supabase - 优先使用新的 secret key 格式
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Gemini API
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    EMBEDDING_DIM = _safe_int(os.getenv("EMBEDDING_DIM"), 768)
    CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.0-flash-exp")

    # RAG 参数
    MATCH_COUNT = _safe_int(os.getenv("MATCH_COUNT"), 5)
    RRF_K = _safe_int(os.getenv("RRF_K"), 60)
    GRAPH_DEPTH = _safe_int(os.getenv("GRAPH_DEPTH"), 2)
    MAX_RETRY = _safe_int(os.getenv("MAX_RETRY"), 2)

    # Journal Graph RAG
    ENTITY_RESOLVE_THRESHOLD = _safe_float(os.getenv("ENTITY_RESOLVE_THRESHOLD"), 0.02)
    EDGE_DECAY_RATE = _safe_float(os.getenv("EDGE_DECAY_RATE"), 0.03)
    SCORE_FLOOR_MULTIPLIER = _safe_float(os.getenv("SCORE_FLOOR_MULTIPLIER"), 0.1)

    # 服务配置
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = _safe_int(os.getenv("PORT"), 8000)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    _REQUIRED = ["SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY"]

    @classmethod
    def validate(cls):
        """Check that required environment variables are set."""
        missing = [k for k in cls._REQUIRED if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


config = Config()
