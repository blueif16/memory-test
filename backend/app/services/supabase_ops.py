from supabase import Client
from app.config import config
from app.services import get_supabase_client


class SupabaseOps:
    """Supabase 操作封装"""

    def __init__(self):
        self.client: Client = get_supabase_client()

    def retrieve_context_mesh(self, query_text: str, query_embedding: list[float]) -> list[dict]:
        """调用混合检索函数"""
        response = self.client.rpc("retrieve_context_mesh", {
            "query_text": query_text,
            "query_embedding": query_embedding,
            "match_count": config.MATCH_COUNT,
            "rrf_k": config.RRF_K,
            "graph_depth": config.GRAPH_DEPTH
        }).execute()
        return response.data

    def insert_document(self, content: str, embedding: list[float], metadata: dict) -> dict:
        """插入文档节点"""
        response = self.client.table("documents").insert({
            "content": content,
            "embedding": embedding,
            "metadata": metadata
        }).execute()
        return response.data[0]

    def insert_relation(self, source_id: int, target_id: int, rel_type: str, properties: dict) -> dict:
        """插入关系边"""
        response = self.client.table("doc_relations").insert({
            "source_id": source_id,
            "target_id": target_id,
            "type": rel_type,
            "properties": properties
        }).execute()
        return response.data[0]

    def find_document_by_content(self, content_snippet: str) -> dict | None:
        """根据内容片段查找文档"""
        response = self.client.table("documents").select("id").ilike("content", f"%{content_snippet}%").limit(1).execute()
        return response.data[0] if response.data else None

supabase_ops = SupabaseOps()
