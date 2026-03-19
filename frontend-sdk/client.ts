export interface ChatResponse {
  response: string;
  retries: number;
}

export interface IngestResponse {
  status: string;
}

export interface HealthResponse {
  status: string;
  persistence: boolean;
}

export class GraphRAGError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'GraphRAGError';
  }
}

class SupabaseGraphRAGClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        signal: AbortSignal.timeout(30_000),
      });
    } catch (err) {
      throw new GraphRAGError(
        0,
        `Network error: ${err instanceof Error ? err.message : String(err)}`
      );
    }
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new GraphRAGError(response.status, `HTTP ${response.status}: ${body}`);
    }
    return response.json() as Promise<T>;
  }

  async chat(conversationId: string, query: string, userId: string = ''): Promise<ChatResponse> {
    return this.request<ChatResponse>('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, query, user_id: userId }),
    });
  }

  async ingest(content: string, source?: string): Promise<IngestResponse> {
    return this.request<IngestResponse>('/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, source }),
    });
  }

  async healthCheck(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }
}

export default SupabaseGraphRAGClient;
