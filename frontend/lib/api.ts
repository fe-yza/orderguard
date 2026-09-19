import type {
  ExperimentResponseOut,
  HighRiskOrderOut,
  MapEntitiesOut,
  OrderDetailOut,
  OrderSummaryOut,
  SimulationConfigIn,
  SimulationMetricsOut,
  SimulationRunSummaryOut,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listSimulations: (limit = 50) =>
    request<SimulationRunSummaryOut[]>(`/simulations?limit=${limit}`),

  getSimulation: (runId: string) =>
    request<SimulationRunSummaryOut>(`/simulations/${runId}`),

  createExperiment: (config: SimulationConfigIn, threshold: number) =>
    request<ExperimentResponseOut>("/simulations", {
      method: "POST",
      body: JSON.stringify({ config, threshold }),
    }),

  getSimulationMetrics: (runId: string) =>
    request<SimulationMetricsOut[]>(`/simulations/${runId}/metrics`),

  listOrders: (
    runId: string,
    opts?: { status?: string; limit?: number; offset?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit) params.set("limit", String(opts.limit));
    if (opts?.offset) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return request<OrderSummaryOut[]>(
      `/simulations/${runId}/orders${qs ? `?${qs}` : ""}`,
    );
  },

  getHighRiskOrders: (runId: string, minScore = 50) =>
    request<HighRiskOrderOut[]>(
      `/simulations/${runId}/high-risk?min_score=${minScore}`,
    ),

  getMapEntities: (runId: string) =>
    request<MapEntitiesOut>(`/simulations/${runId}/map`),

  // Order IDs like "order-000042" are only unique within a single
  // simulation run (see backend/src/orderguard/persistence/models.py), so
  // every order lookup must be scoped by run_id — there is no flat
  // /orders/{id} endpoint.
  getOrder: (runId: string, orderId: string) =>
    request<OrderDetailOut>(`/simulations/${runId}/orders/${orderId}`),
};

export { ApiError };
