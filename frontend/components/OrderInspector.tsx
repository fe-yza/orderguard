"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError } from "@/lib/api";
import type { InterventionDecisionOut, OrderDetailOut } from "@/lib/types";
import { InfoTooltip } from "@/components/tour/InfoTooltip";
import { useTour } from "@/lib/tour/TourContext";

export function OrderInspector({
  runId,
  orderId,
}: {
  runId: string;
  orderId: string;
}) {
  const [order, setOrder] = useState<OrderDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tour = useTour();

  useEffect(() => {
    api
      .getOrder(runId, orderId)
      .then(setOrder)
      .catch((e) =>
        setError(e instanceof ApiError ? `API error ${e.status}: ${e.message}` : String(e)),
      );
  }, [runId, orderId]);

  useEffect(() => {
    if (!order) return;
    tour.notifyOrderOpened(runId, orderId, order.risk_assessments.length > 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order, runId, orderId]);

  if (error) return <p className="text-[var(--danger)] text-[12px]">{error}</p>;
  if (!order) return <p className="text-[var(--text-dim)] text-[12px]">Loading…</p>;

  const latestRisk = order.risk_assessments.at(-1);
  const latestDecision = order.intervention_decisions.at(-1);

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      <div data-tour="order-header">
        <Link href={`/?run=${runId}`} className="text-[12px] text-[var(--accent)]">
          ← Overview
        </Link>
        <h1 className="text-[15px] font-semibold mt-2 mono">{order.id}</h1>
        <p className="text-[12px] text-[var(--text-dim)] mt-1">
          {order.status}
          {order.failure_reason ? ` · failed: ${order.failure_reason}` : ""}
          {order.cancellation_reason ? ` · cancelled: ${order.cancellation_reason}` : ""}
          {order.is_perishable ? " · perishable" : ""}
        </p>
      </div>

      <Section title="Timeline" badge="measured" dataTour="order-timeline">
        <table>
          <thead>
            <tr>
              <th>Event</th>
              <th>Time</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {order.events.map((event, i) => (
              <tr key={i}>
                <td className="mono">{event.event_type}</td>
                <td className="mono">{new Date(event.occurred_at).toLocaleString()}</td>
                <td className="mono text-[var(--text-faint)]">
                  {Object.keys(event.details).length > 0
                    ? JSON.stringify(event.details)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {order.risk_assessments.length > 1 ? (
        <Section title="Risk score over time" badge="model estimate" dataTour="risk-history-chart">
          <div className="h-[160px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={order.risk_assessments.map((a) => ({
                  time: new Date(a.computed_at).toLocaleTimeString(),
                  score: a.overall_risk_score,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fill: "var(--text-dim)", fontSize: 10 }} />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: "var(--text-dim)", fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-panel-raised)",
                    border: "1px solid var(--border)",
                    fontSize: 12,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="var(--danger)"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-[var(--text-faint)] mt-1">
            Recomputed each time an event fired for this order (event-reactive, not polled) — a
            flat stretch means nothing happened for this order in that gap, not that risk was
            reassessed and unchanged.
          </p>
        </Section>
      ) : null}

      <Section title="Latest risk assessment" badge="model estimate" dataTour="risk-assessment">
        {latestRisk ? (
          <div className="flex flex-col gap-3">
            <div className="flex gap-6">
              <Stat label="Score" value={latestRisk.overall_risk_score.toFixed(1)} />
              <Stat label="Predicted" value={latestRisk.predicted_failure_type ?? "none"} />
              <Stat label="Confidence" value={`${(latestRisk.confidence * 100).toFixed(0)}%`} />
              <Stat
                label="Predicted delay"
                value={`${latestRisk.predicted_delay_minutes.toFixed(1)} min`}
              />
            </div>
            <table>
              <thead>
                <tr>
                  <th>Factor</th>
                  <th>Weight</th>
                  <th>Signal</th>
                  <th>Contribution</th>
                </tr>
              </thead>
              <tbody>
                {latestRisk.factors.map((f) => (
                  <tr key={f.name}>
                    <td>{f.name}</td>
                    <td className="mono">{f.weight.toFixed(1)}</td>
                    <td className="mono">{f.raw_signal.toFixed(2)}</td>
                    <td className="mono">{f.contribution.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[var(--text-faint)] text-[12px]">No risk assessments recorded.</p>
        )}
      </Section>

      <Section
        title="Recommended intervention — expected-value reasoning"
        badge="model estimate"
        dataTour="intervention-section"
      >
        {latestDecision ? (
          <InterventionMath decision={latestDecision} />
        ) : (
          <p className="text-[var(--text-faint)] text-[12px]">
            No intervention decisions recorded.
          </p>
        )}
      </Section>
    </div>
  );
}

function Section({
  title,
  badge,
  dataTour,
  children,
}: {
  title: string;
  badge?: "measured" | "model estimate";
  dataTour?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel p-4 overflow-x-auto" data-tour={dataTour}>
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)]">{title}</h2>
        {badge ? (
          <span
            className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded"
            style={{
              background: badge === "measured" ? "var(--bg-panel-raised)" : "transparent",
              color: badge === "measured" ? "var(--success)" : "var(--warning)",
              border: `1px solid ${badge === "measured" ? "var(--success)" : "var(--warning)"}`,
            }}
          >
            {badge}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function InterventionMath({ decision }: { decision: InterventionDecisionOut }) {
  const doNothing = decision.candidates.find((c) => c.intervention_type === "do_nothing");
  const chosenCandidate = decision.candidates.find(
    (c) => c.intervention_type === decision.chosen,
  );
  const netValue =
    doNothing && chosenCandidate
      ? doNothing.total_expected_cost - chosenCandidate.total_expected_cost
      : null;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12px] flex items-center gap-1.5">
        Chosen: <span className="mono text-[var(--accent)]">{decision.chosen}</span>
        <InfoTooltip title="What is expected value?">
          (Cost of doing nothing) − (direct cost + residual expected failure cost of acting).
          OrderGuard picks whichever option — including doing nothing — has the lowest total
          expected cost.
        </InfoTooltip>
      </p>
      <p className="text-[11px] text-[var(--text-dim)]">{decision.rationale}</p>

      {netValue !== null ? (
        <div className="flex gap-6">
          <Stat
            label="Direct cost"
            value={`$${chosenCandidate!.direct_cost.toFixed(2)}`}
          />
          <Stat
            label="Est. residual failure cost"
            value={`$${chosenCandidate!.residual_expected_failure_cost.toFixed(2)}`}
          />
          <Stat
            label="Baseline (do nothing) cost"
            value={`$${doNothing!.total_expected_cost.toFixed(2)}`}
          />
          <Stat
            label="Expected net value vs. doing nothing"
            value={`${netValue >= 0 ? "+" : ""}$${netValue.toFixed(2)}`}
            tone={netValue >= 0 ? "success" : "danger"}
          />
        </div>
      ) : null}

      <table>
        <thead>
          <tr>
            <th>Intervention</th>
            <th>Direct cost</th>
            <th>
              Implied P(failure)
              <InfoTooltip title="Implied P(failure)">
                The risk score ÷ 100, treated as an implied probability. This is a deliberate
                modeling simplification, not a calibrated probability of failure.
              </InfoTooltip>
            </th>
            <th>Est. prob. reduction</th>
            <th>Est. cost reduction</th>
            <th>Failure cost</th>
            <th>Residual cost</th>
            <th>Total expected cost</th>
          </tr>
        </thead>
        <tbody>
          {decision.candidates
            .slice()
            .sort((a, b) => a.total_expected_cost - b.total_expected_cost)
            .map((c) => (
              <tr
                key={c.intervention_type}
                style={
                  c.intervention_type === decision.chosen
                    ? { background: "var(--bg-panel-raised)" }
                    : undefined
                }
              >
                <td className="mono">{c.intervention_type}</td>
                <td className="mono">${c.direct_cost.toFixed(2)}</td>
                <td className="mono">{(c.failure_probability * 100).toFixed(1)}%</td>
                <td className="mono">
                  {c.probability_reduction > 0 ? `${(c.probability_reduction * 100).toFixed(0)}%` : "—"}
                </td>
                <td className="mono">
                  {c.cost_reduction_fraction > 0
                    ? `${(c.cost_reduction_fraction * 100).toFixed(0)}%`
                    : "—"}
                </td>
                <td className="mono">${c.failure_cost.toFixed(2)}</td>
                <td className="mono">${c.residual_expected_failure_cost.toFixed(2)}</td>
                <td className="mono font-semibold">${c.total_expected_cost.toFixed(2)}</td>
              </tr>
            ))}
        </tbody>
      </table>
      <p className="text-[11px] text-[var(--text-faint)]">
        &quot;Est. prob. reduction&quot; and &quot;est. cost reduction&quot; are documented
        modeling assumptions about each lever&apos;s effect (see
        docs/interview-notes.md), not measurements from real outcome data — there is no real
        marketplace to learn them from. The chosen row is whichever minimizes total expected
        cost, including the implicit &quot;do nothing&quot; option.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "success" | "danger";
}) {
  const color = tone === "success" ? "var(--success)" : tone === "danger" ? "var(--danger)" : undefined;
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase text-[var(--text-faint)]">{label}</span>
      <span className="mono text-[13px]" style={{ color }}>
        {value}
      </span>
    </div>
  );
}
