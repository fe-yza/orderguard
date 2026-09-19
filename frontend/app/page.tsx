"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type {
  HighRiskOrderOut,
  MapEntitiesOut,
  SimulationMetricsOut,
  SimulationRunSummaryOut,
} from "@/lib/types";
import { StatTile } from "@/components/StatTile";
import { MapView } from "@/components/MapView";

const POLL_INTERVAL_MS = 20_000;
const HIGH_RISK_THRESHOLD = 50;

export default function OverviewPage() {
  return (
    <Suspense fallback={<p className="text-[var(--text-dim)]">Loading…</p>}>
      <OverviewInner />
    </Suspense>
  );
}

function OverviewInner() {
  const searchParams = useSearchParams();
  const requestedRunId = searchParams.get("run");

  const [runs, setRuns] = useState<SimulationRunSummaryOut[] | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SimulationMetricsOut[] | null>(null);
  const [highRisk, setHighRisk] = useState<HighRiskOrderOut[] | null>(null);
  const [mapEntities, setMapEntities] = useState<MapEntitiesOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  useEffect(() => {
    api
      .listSimulations()
      .then((list) => {
        setRuns(list);
        if (requestedRunId && list.some((r) => r.id === requestedRunId)) {
          setSelectedRunId(requestedRunId);
        } else if (list.length > 0) {
          setSelectedRunId(list[0].id);
        }
      })
      .catch((e) => setError(describeError(e)));
    // Only re-run if the requested run changes; `runs` list itself is
    // fetched once on mount.
     
  }, [requestedRunId]);

  const refresh = useCallback((runId: string) => {
    Promise.all([
      api.getSimulationMetrics(runId),
      api.getHighRiskOrders(runId, HIGH_RISK_THRESHOLD),
      api.getMapEntities(runId),
    ])
      .then(([m, hr, map]) => {
        setMetrics(m);
        setHighRisk(hr);
        setMapEntities(map);
        setLastRefreshed(new Date());
        setError(null);
      })
      .catch((e) => setError(describeError(e)));
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    refresh(selectedRunId);
    const interval = setInterval(() => refresh(selectedRunId), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [selectedRunId, refresh]);

  const expectedValueMetrics = metrics?.find((m) => m.strategy === "expected_value");

  if (runs === null) {
    return <p className="text-[var(--text-dim)]">Loading…</p>;
  }

  if (runs.length === 0) {
    return (
      <div className="panel p-6 max-w-lg">
        <p className="text-[var(--text-dim)]">
          No simulations yet. Go to{" "}
          <Link href="/simulation-lab" className="text-[var(--accent)]">
            Simulation Lab
          </Link>{" "}
          to run one.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <select
          className="panel px-3 py-1.5 text-[12px] mono"
          value={selectedRunId ?? ""}
          onChange={(e) => setSelectedRunId(e.target.value)}
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} · seed {r.seed} · {new Date(r.created_at).toLocaleString()}
            </option>
          ))}
        </select>
        <button
          className="panel px-3 py-1.5 text-[12px] hover:bg-[var(--bg-panel-raised)]"
          onClick={() => selectedRunId && refresh(selectedRunId)}
        >
          Refresh
        </button>
        {lastRefreshed ? (
          <span className="text-[11px] text-[var(--text-faint)]">
            updated {lastRefreshed.toLocaleTimeString()}
          </span>
        ) : null}
        {error ? <span className="text-[12px] text-[var(--danger)]">{error}</span> : null}
      </div>

      {expectedValueMetrics ? (
        <div className="flex flex-wrap gap-3">
          <StatTile
            label="Active Deliveries"
            value={String(expectedValueMetrics.in_flight_count)}
          />
          <StatTile
            label="High-Risk Orders"
            value={String(highRisk?.length ?? "—")}
            tone={highRisk && highRisk.length > 0 ? "warning" : "default"}
            sub={`score ≥ ${HIGH_RISK_THRESHOLD}`}
          />
          <StatTile
            label="Failure Rate"
            value={`${(expectedValueMetrics.failure_rate * 100).toFixed(1)}%`}
            tone={expectedValueMetrics.failure_rate > 0.02 ? "danger" : "success"}
          />
          <StatTile
            label="Interventions Triggered"
            value={String(expectedValueMetrics.intervention_count)}
            sub={`$${expectedValueMetrics.total_intervention_cost.toFixed(2)} spent`}
          />
          <StatTile
            label="Late Rate"
            value={`${(expectedValueMetrics.late_rate * 100).toFixed(1)}%`}
          />
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="panel p-3">
          <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)] mb-2">
            Marketplace map
          </h2>
          {mapEntities ? (
            <MapView entities={mapEntities} />
          ) : (
            <div className="h-[360px] flex items-center justify-center text-[var(--text-faint)]">
              loading map…
            </div>
          )}
        </div>

        <div className="panel p-3 overflow-x-auto">
          <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)] mb-2">
            High-risk order feed
          </h2>
          {highRisk === null ? (
            <p className="text-[var(--text-faint)] text-[12px]">loading…</p>
          ) : highRisk.length === 0 ? (
            <p className="text-[var(--text-faint)] text-[12px]">
              No orders above the risk threshold right now.
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Status</th>
                  <th>Risk</th>
                  <th>Predicted</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {highRisk.map(({ order, latest_risk_assessment }) => (
                  <tr key={order.id}>
                    <td>
                      <Link
                        href={`/simulations/${selectedRunId}/orders/${order.id}`}
                        className="text-[var(--accent)] mono"
                      >
                        {order.id}
                      </Link>
                    </td>
                    <td className="mono">{order.status}</td>
                    <td className="mono">
                      {latest_risk_assessment.overall_risk_score.toFixed(1)}
                    </td>
                    <td>{latest_risk_assessment.predicted_failure_type ?? "—"}</td>
                    <td className="mono">
                      {(latest_risk_assessment.confidence * 100).toFixed(0)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function describeError(e: unknown): string {
  if (e instanceof ApiError) return `API error ${e.status}: ${e.message}`;
  if (e instanceof Error) return e.message;
  return "Unknown error";
}
