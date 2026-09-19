"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { ExperimentResponseOut, SimulationConfigIn } from "@/lib/types";

const DEFAULT_CONFIG: SimulationConfigIn = {
  seed: 42,
  start_time: "2026-01-01T08:00:00",
  duration_minutes: 300,
  num_merchants: 15,
  num_drivers: 25,
  num_customers: 200,
  base_order_rate_per_minute: 1.0,
  map_size_km: 10.0,
};

const STRATEGY_LABEL: Record<string, string> = {
  no_intervention: "No intervention",
  threshold_based: "Threshold-based",
  expected_value: "OrderGuard (expected-value)",
};

export default function SimulationLabPage() {
  const router = useRouter();
  const [config, setConfig] = useState<SimulationConfigIn>(DEFAULT_CONFIG);
  const [threshold, setThreshold] = useState(50);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExperimentResponseOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateField<K extends keyof SimulationConfigIn>(
    key: K,
    value: SimulationConfigIn[K],
  ) {
    setConfig((c) => ({ ...c, [key]: value }));
  }

  async function runExperiment() {
    setRunning(true);
    setError(null);
    try {
      const response = await api.createExperiment(config, threshold);
      setResult(response);
    } catch (e) {
      setError(e instanceof ApiError ? `API error ${e.status}: ${e.message}` : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 max-w-5xl">
      <div className="panel p-4">
        <h1 className="text-[13px] font-semibold mb-3">
          Configure &amp; run experiment
        </h1>
        <p className="text-[12px] text-[var(--text-dim)] mb-4">
          Runs the same seeded marketplace three ways — no intervention,
          threshold-based, and OrderGuard&apos;s expected-value engine — and
          compares real, measured outcomes. No fabricated numbers: every value
          below comes from the run you trigger here.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Field label="Seed">
            <input
              type="number"
              className="input"
              value={config.seed}
              onChange={(e) => updateField("seed", Number(e.target.value))}
            />
          </Field>
          <Field label="Duration (min)">
            <input
              type="number"
              className="input"
              value={config.duration_minutes}
              onChange={(e) => updateField("duration_minutes", Number(e.target.value))}
            />
          </Field>
          <Field label="Merchants">
            <input
              type="number"
              className="input"
              value={config.num_merchants}
              onChange={(e) => updateField("num_merchants", Number(e.target.value))}
            />
          </Field>
          <Field label="Drivers">
            <input
              type="number"
              className="input"
              value={config.num_drivers}
              onChange={(e) => updateField("num_drivers", Number(e.target.value))}
            />
          </Field>
          <Field label="Customers">
            <input
              type="number"
              className="input"
              value={config.num_customers}
              onChange={(e) => updateField("num_customers", Number(e.target.value))}
            />
          </Field>
          <Field label="Order rate (/min)">
            <input
              type="number"
              step="0.1"
              className="input"
              value={config.base_order_rate_per_minute}
              onChange={(e) =>
                updateField("base_order_rate_per_minute", Number(e.target.value))
              }
            />
          </Field>
          <Field label="Map size (km)">
            <input
              type="number"
              className="input"
              value={config.map_size_km}
              onChange={(e) => updateField("map_size_km", Number(e.target.value))}
            />
          </Field>
          <Field label="Intervention threshold">
            <input
              type="number"
              className="input"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </Field>
        </div>
        <button
          className="mt-4 px-4 py-2 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium disabled:opacity-50"
          onClick={runExperiment}
          disabled={running}
        >
          {running ? "Running…" : "Run experiment"}
        </button>
        {error ? <p className="mt-2 text-[12px] text-[var(--danger)]">{error}</p> : null}
      </div>

      {result ? (
        <div className="panel p-4 overflow-x-auto">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[13px] font-semibold">Comparative results</h2>
            <button
              className="text-[12px] text-[var(--accent)]"
              onClick={() => router.push(`/?run=${result.simulation_run_id}`)}
            >
              View run {result.simulation_run_id} on Overview →
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Orders</th>
                <th>Delivered</th>
                <th>Failed</th>
                <th>Cancelled</th>
                <th>Late rate</th>
                <th>Failure rate</th>
                <th>Avg delay (min)</th>
                <th>P95 delay (min)</th>
                <th>Interventions</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {result.metrics.map((m) => (
                <tr key={m.strategy}>
                  <td>{STRATEGY_LABEL[m.strategy] ?? m.strategy}</td>
                  <td className="mono">{m.total_orders}</td>
                  <td className="mono">{m.delivered_count}</td>
                  <td className="mono">{m.failed_count}</td>
                  <td className="mono">{m.cancelled_count}</td>
                  <td className="mono">{(m.late_rate * 100).toFixed(1)}%</td>
                  <td className="mono">{(m.failure_rate * 100).toFixed(1)}%</td>
                  <td className="mono">{m.avg_delay_minutes.toFixed(1)}</td>
                  <td className="mono">{m.p95_delay_minutes.toFixed(1)}</td>
                  <td className="mono">{m.intervention_count}</td>
                  <td className="mono">${m.total_intervention_cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[11px] text-[var(--text-faint)]">
            Strategies re-seed independently from the same config, so they
            start identically and diverge only once an intervention actually
            changes an outcome — see docs/interview-notes.md for why totals
            can differ slightly between rows.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-[var(--text-dim)]">{label}</span>
      {children}
    </label>
  );
}
