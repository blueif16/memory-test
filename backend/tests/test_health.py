"""Basic smoke tests for the RAG API."""
from unittest.mock import patch, MagicMock


def _mock_supabase():
    """Patch Supabase and LLM clients so FastAPI can import without real credentials."""
    mock_client = MagicMock()
    mock_client.table.return_value = mock_client
    mock_client.rpc.return_value = mock_client
    mock_client.select.return_value = mock_client
    mock_client.insert.return_value = mock_client
    mock_client.execute.return_value = MagicMock(data=[], count=0)
    return mock_client


@patch("app.services.get_supabase_client", return_value=_mock_supabase())
@patch("app.core.rag_store.create_client", return_value=_mock_supabase())
@patch("app.core.rag_store.GeminiEmbeddings")
@patch("app.graph.workflow.ConnectionPool", side_effect=Exception("no db"))
@patch("app.graph.workflow.PostgresSaver", side_effect=Exception("no db"))
def test_health_endpoint(*mocks):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "persistence" in data
