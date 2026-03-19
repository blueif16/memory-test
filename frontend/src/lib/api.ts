const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:9000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path}: ${res.status}`);
  return res.json();
}

export const api = {
  getUsers: () => get<{ users: string[] }>("/journal/users"),
  getSnapshots: (userId: string, start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start_date", start);
    if (end) params.set("end_date", end);
    const qs = params.toString();
    return get<{ snapshots: import("./types").Snapshot[] }>(
      `/journal/snapshots/${userId}${qs ? `?${qs}` : ""}`
    );
  },
  getGraph: (userId: string) =>
    get<{ items: import("./types").DomainItem[] }>(`/journal/graph/${userId}`),
  score: (userId: string) =>
    post<{ items: unknown[] }>("/journal/score", { user_id: userId }),
  runEval: (archetype: string, numDays: number) =>
    post<unknown>("/journal/eval/run", { archetype, num_days: numDays }),
  startOptimize: (numIterations: number, archetype: string, numDays: number) =>
    post<{ run_id: string; status: string }>("/journal/eval/optimize", {
      num_iterations: numIterations,
      archetype,
      num_days: numDays,
    }),
  getOptimizeStatus: (runId: string) =>
    get<{ status: string; result: unknown }>(`/journal/eval/optimize/${runId}`),
  health: () => get<{ status: string }>("/health"),
};
