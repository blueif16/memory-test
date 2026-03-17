import os
from dotenv import load_dotenv, find_dotenv

# 从当前工作目录开始向上搜索 .env 文件
# 这样无论从哪里执行，都能找到项目根目录的 .env
load_dotenv(find_dotenv(usecwd=True))

class Config:
    """统一配置管理"""
    # Supabase - 优先使用新的 secret key 格式
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Gemini API
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
    CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.0-flash-exp")

    # RAG 参数
    MATCH_COUNT = int(os.getenv("MATCH_COUNT", "5"))
    RRF_K = int(os.getenv("RRF_K", "60"))
    GRAPH_DEPTH = int(os.getenv("GRAPH_DEPTH", "2"))
    MAX_RETRY = int(os.getenv("MAX_RETRY", "2"))

    # Journal Graph RAG
    ENTITY_RESOLVE_THRESHOLD = float(os.getenv("ENTITY_RESOLVE_THRESHOLD", "0.02"))
    EDGE_DECAY_RATE = float(os.getenv("EDGE_DECAY_RATE", "0.03"))
    SCORE_FLOOR_MULTIPLIER = float(os.getenv("SCORE_FLOOR_MULTIPLIER", "0.1"))

    # 服务配置
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000")

config = Config()
