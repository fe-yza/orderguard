"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError } from "@/lib/api";
import type { ExperimentResponseOut, RushHourWindowIn, SimulationConfigIn } from "@/lib/types";
import { InfoTooltip } from "@/components/tour/InfoTooltip";
import { useTour } from "@/lib/tour/TourContext";

const DEFAULT_CONFIG: SimulationConfigIn = {
  seed: 42,
  start_time: "2026-01-01T08:00:00",
  duration_minutes: 480,
  num_merchants: 20,
  num_drivers: 35,
  num_customers: 300,
  base_order_rate_per_minute: 1.0,
  map_size_km: 10.0,
  avg_merchant_prep_minutes: 12.0,
  merchant_prep_stddev_minutes: 3.0,
  driver_offline_probability_per_tick: 0.0008,
  merchant_stockout_probability: 0.03,
  customer_unreachable_probability: 0.02,
  perishable_spoilage_probability_per_tick: 0.05,
};

const DEFAULT_RUSH_HOUR: RushHourWindowIn = {
  start_minute: 60,
  end_minute: 180,
  demand_multiplier: 1.8,
  speed_multiplier: 0.65,
};

const STRATEGY_LABEL: Record<string, string> = {
  no_intervention: "No intervention",
  threshold_based: "Threshold-based",
  expected_value: "OrderGuard (expected-value)",
};

const STRATEGY_COLOR: Record<string, string> = {
  no_intervention: "#5b6270",
  threshold_based: "#e0a83c",
  expected_value: "#5b9dff",
};

type RunStatus = "idle" | "running" | "success" | "error";

export default function SimulationLabPage() {
  const router = useRouter();
  const tour = useTour();
  const [config, setConfig] = useState<SimulationConfigIn>(DEFAULT_CONFIG);
  const [threshold, setThreshold] = useState(50);
  const [rushHourEnabled, setRushHourEnabled] = useState(false);
  const [rushHour, setRushHour] = useState<RushHourWindowIn>(DEFAULT_RUSH_HOUR);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [result, setResult] = useState<ExperimentResponseOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateField<K extends keyof SimulationConfigIn>(
    key: K,
    value: SimulationConfigIn[K],
  ) {
    setConfig((c) => ({ ...c, [key]: value }));
  }

  function updateRushHour<K extends keyof RushHourWindowIn>(key: K, value: RushHourWindowIn[K]) {
    setRushHour((w) => ({ ...w, [key]: value }));
  }

  async function runExperiment() {
    setStatus("running");
    setError(null);
    tour.notifyExperimentStatus("running");
    try {
      const fullConfig: SimulationConfigIn = {
        ...config,
        rush_hour_windows: rushHourEnabled ? [rushHour] : [],
      };
      const response = await api.createExperiment(fullConfig, threshold);
      setResult(response);
      setStatus("success");
      tour.notifyExperimentStatus("success", response.simulation_run_id);
    } catch (e) {
      setError(e instanceof ApiError ? `API error ${e.status}: ${e.message}` : String(e));
      setStatus("error");
      tour.notifyExperimentStatus("error");
    }
  }

  const chartData = result
    ? ["late_rate", "failure_rate", "cancellation_rate"].map((key) => ({
        metric: { late_rate: "Late", failure_rate: "Failed", cancellation_rate: "Cancelled" }[
          key
        ],
        ...Object.fromEntries(
          result.metrics.map((m) => [
            m.strategy,
            Number((m[key as keyof typeof m] as number) * 100).toFixed(2),
          ]),
        ),
      }))
    : [];

  return (
    <div className="flex flex-col gap-5 max-w-6xl">
      <div className="panel p-4">
        <h1 className="text-[13px] font-semibold mb-1">Configure &amp; run experiment</h1>
        <p className="text-[12px] text-[var(--text-dim)] mb-4">
          Runs the same seeded marketplace three ways — no intervention,
          threshold-based, and OrderGuard&apos;s expected-value engine — and reports real,
          measured outcomes from an actual simulation run. Nothing here is precomputed or
          fabricated; every field below maps directly to a parameter the backend simulation
          engine accepts.
        </p>

        <div data-tour="sim-config-scale">
          <ConfigSection title="Marketplace scale">
            <Field label="Random seed">
              <input
                type="number"
                className="input"
                value={config.seed}
                onChange={(e) => updateField("seed", Number(e.target.value))}
              />
            </Field>
            <Field label="Duration (sim. minutes)">
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
            <Field label="Drivers (supply)">
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
            <Field label="Map size (km)">
              <input
                type="number"
                className="input"
                value={config.map_size_km}
                onChange={(e) => updateField("map_size_km", Number(e.target.value))}
              />
            </Field>
          </ConfigSection>

          <ConfigSection title="Demand">
            <Field label="Order arrival rate (/min)">
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
            <label className="flex items-center gap-2 text-[11px] text-[var(--text-dim)] self-end pb-1.5">
              <input
                type="checkbox"
                checked={rushHourEnabled}
                onChange={(e) => setRushHourEnabled(e.target.checked)}
              />
              Enable rush-hour window
            </label>
            {rushHourEnabled ? (
              <>
                <Field label="Rush start (min)">
                  <input
                    type="number"
                    className="input"
                    value={rushHour.start_minute}
                    onChange={(e) => updateRushHour("start_minute", Number(e.target.value))}
                  />
                </Field>
                <Field label="Rush end (min)">
                  <input
                    type="number"
                    className="input"
                    value={rushHour.end_minute}
                    onChange={(e) => updateRushHour("end_minute", Number(e.target.value))}
                  />
                </Field>
                <Field label="Demand multiplier">
                  <input
                    type="number"
                    step="0.1"
                    className="input"
                    value={rushHour.demand_multiplier}
                    onChange={(e) => updateRushHour("demand_multiplier", Number(e.target.value))}
                  />
                </Field>
                <Field label="Travel speed multiplier">
                  <input
                    type="number"
                    step="0.05"
                    min="0.05"
                    max="1"
                    className="input"
                    value={rushHour.speed_multiplier}
                    onChange={(e) => updateRushHour("speed_multiplier", Number(e.target.value))}
                  />
                </Field>
              </>
            ) : null}
          </ConfigSection>

          <ConfigSection title="Merchant behavior">
            <Field label="Avg prep time (min)">
              <input
                type="number"
                className="input"
                value={config.avg_merchant_prep_minutes}
                onChange={(e) => updateField("avg_merchant_prep_minutes", Number(e.target.value))}
              />
            </Field>
            <Field label="Prep time variance (stddev)">
              <input
                type="number"
                className="input"
                value={config.merchant_prep_stddev_minutes}
                onChange={(e) =>
                  updateField("merchant_prep_stddev_minutes", Number(e.target.value))
                }
              />
            </Field>
          </ConfigSection>
        </div>

        <div data-tour="hazard-rates">
          <ConfigSection
            title="Failure hazard rates (ground truth)"
            hint={
              <>
                These control how often problems occur inside the simulator — the hidden ground
                truth used to generate outcomes.{" "}
                <strong className="text-[var(--warning)]">
                  The risk engine never receives these values directly
                </strong>{" "}
                — it must infer risk from observable marketplace state, the same way a real
                system would. Not all four are checked the same way: two are re-rolled every
                simulated minute, two are rolled once at a specific moment.
              </>
            }
          >
            <Field label="Driver goes offline (per tick, while delivering)">
              <input
                type="number"
                step="0.0001"
                className="input"
                value={config.driver_offline_probability_per_tick}
                onChange={(e) =>
                  updateField("driver_offline_probability_per_tick", Number(e.target.value))
                }
              />
            </Field>
            <Field label="Merchant stockout (once, at order confirmation)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={config.merchant_stockout_probability}
                onChange={(e) =>
                  updateField("merchant_stockout_probability", Number(e.target.value))
                }
              />
            </Field>
            <Field label="Customer unreachable (once, at arrival)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={config.customer_unreachable_probability}
                onChange={(e) =>
                  updateField("customer_unreachable_probability", Number(e.target.value))
                }
              />
            </Field>
            <Field label="Perishable spoilage (per tick, once already late)">
              <input
                type="number"
                step="0.01"
                className="input"
                value={config.perishable_spoilage_probability_per_tick}
                onChange={(e) =>
                  updateField("perishable_spoilage_probability_per_tick", Number(e.target.value))
                }
              />
            </Field>
          </ConfigSection>
        </div>

        <div data-tour="baseline-threshold">
          <ConfigSection
            title="Baseline policy"
            hint="Risk-score threshold used only by the naive 'threshold-based' baseline — OrderGuard's own expected-value strategy doesn't use a fixed threshold to decide anything."
          >
            <Field label="Threshold-based trigger score">
              <input
                type="number"
                className="input"
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </Field>
          </ConfigSection>
        </div>

        <button
          data-tour="run-button"
          className="mt-2 px-4 py-2 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium disabled:opacity-50"
          onClick={runExperiment}
          disabled={status === "running"}
        >
          {status === "running" ? "Running simulation…" : "Run experiment"}
        </button>

        <StatusBanner status={status} error={error} runId={result?.simulation_run_id} />
      </div>

      {result ? (
        <div data-tour="results-section" className="panel p-4 overflow-x-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-1.5">
              <h2 className="text-[13px] font-semibold">Comparative results</h2>
              <InfoTooltip title="How are strategies compared?">
                All three strategies re-seed from the same config, so they start identical and
                diverge only once an intervention actually changes an outcome — that divergence
                is the point of the comparison.
              </InfoTooltip>
            </div>
            <button
              className="text-[12px] text-[var(--accent)]"
              onClick={() => router.push(`/?run=${result.simulation_run_id}`)}
            >
              Inspect this run on Overview →
            </button>
          </div>

          <div className="h-[220px] mb-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="metric" tick={{ fill: "var(--text-dim)", fontSize: 11 }} />
                <YAxis
                  tick={{ fill: "var(--text-dim)", fontSize: 11 }}
                  label={{
                    value: "% of orders",
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--text-dim)",
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-panel-raised)",
                    border: "1px solid var(--border)",
                    fontSize: 12,
                  }}
                />
                <Legend
                  formatter={(value) => STRATEGY_LABEL[value] ?? value}
                  wrapperStyle={{ fontSize: 11 }}
                />
                {result.metrics.map((m) => (
                  <Bar
                    key={m.strategy}
                    dataKey={m.strategy}
                    name={m.strategy}
                    fill={STRATEGY_COLOR[m.strategy] ?? "#5b9dff"}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
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
                <th>
                  Avg schedule deviation (min)
                  <InfoTooltip title="Avg schedule deviation">
                    Mean (delivered time − promised time) over delivered orders, in minutes.
                    Negative means early, positive means late.
                  </InfoTooltip>
                </th>
                <th>
                  P95 deviation (min)
                  <InfoTooltip title="P95 deviation">
                    The deviation value that 95% of delivered orders did better than — a way to
                    see the bad tail without one outlier skewing the average.
                  </InfoTooltip>
                </th>
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
                  <td className="mono">
                    {m.avg_delay_minutes >= 0 ? "+" : ""}
                    {m.avg_delay_minutes.toFixed(1)}
                    <span className="text-[var(--text-faint)]">
                      {" "}
                      ({m.avg_delay_minutes < 0 ? "early" : "late"})
                    </span>
                  </td>
                  <td className="mono">
                    {m.p95_delay_minutes >= 0 ? "+" : ""}
                    {m.p95_delay_minutes.toFixed(1)}
                  </td>
                  <td className="mono">{m.intervention_count}</td>
                  <td className="mono">${m.total_intervention_cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[11px] text-[var(--text-faint)]">
            These numbers are never adjusted to favor any strategy — the expected-value engine
            can and sometimes does perform about the same as, or worse than, a baseline in a
            given run. Strategies re-seed independently from the same config, so they start
            identically and diverge only once an intervention actually changes an outcome (see
            docs/interview-notes.md for why totals can differ slightly between rows).
          </p>
        </div>
      ) : null}
    </div>
  );
}

function StatusBanner({
  status,
  error,
  runId,
}: {
  status: RunStatus;
  error: string | null;
  runId?: string;
}) {
  if (status === "idle") return null;
  const styles: Record<RunStatus, string> = {
    idle: "",
    running: "text-[var(--text-dim)]",
    success: "text-[var(--success)]",
    error: "text-[var(--danger)]",
  };
  const text =
    status === "running"
      ? "Running simulation — three full strategy runs plus persistence, typically 1–5s depending on scale…"
      : status === "success"
        ? `Simulation complete — run ${runId}`
        : `Simulation failed: ${error}`;
  return <p className={`mt-2 text-[12px] ${styles[status]}`}>{text}</p>;
}

function ConfigSection({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-baseline gap-2 mb-2">
        <h3 className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]">{title}</h3>
        {hint ? <span className="text-[10px] text-[var(--text-faint)]">{hint}</span> : null}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>
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
