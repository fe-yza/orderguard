"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { OrderDetailOut } from "@/lib/types";

export function OrderInspector({
  runId,
  orderId,
}: {
  runId: string;
  orderId: string;
}) {
  const [order, setOrder] = useState<OrderDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getOrder(runId, orderId)
      .then(setOrder)
      .catch((e) =>
        setError(e instanceof ApiError ? `API error ${e.status}: ${e.message}` : String(e)),
      );
  }, [runId, orderId]);

  if (error) return <p className="text-[var(--danger)] text-[12px]">{error}</p>;
  if (!order) return <p className="text-[var(--text-dim)] text-[12px]">Loading…</p>;

  const latestRisk = order.risk_assessments.at(-1);
  const latestDecision = order.intervention_decisions.at(-1);

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      <div>
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

      <Section title="Timeline">
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

      <Section title="Latest risk assessment">
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

      <Section title="Recommended intervention — cost math">
        {latestDecision ? (
          <div className="flex flex-col gap-3">
            <p className="text-[12px]">
              Chosen: <span className="mono text-[var(--accent)]">{latestDecision.chosen}</span>
            </p>
            <p className="text-[11px] text-[var(--text-dim)]">{latestDecision.rationale}</p>
            <table>
              <thead>
                <tr>
                  <th>Intervention</th>
                  <th>Direct cost</th>
                  <th>P(failure)</th>
                  <th>Failure cost</th>
                  <th>Residual cost</th>
                  <th>Total expected cost</th>
                </tr>
              </thead>
              <tbody>
                {latestDecision.candidates
                  .slice()
                  .sort((a, b) => a.total_expected_cost - b.total_expected_cost)
                  .map((c) => (
                    <tr
                      key={c.intervention_type}
                      style={
                        c.intervention_type === latestDecision.chosen
                          ? { background: "var(--bg-panel-raised)" }
                          : undefined
                      }
                    >
                      <td className="mono">{c.intervention_type}</td>
                      <td className="mono">${c.direct_cost.toFixed(2)}</td>
                      <td className="mono">{(c.failure_probability * 100).toFixed(1)}%</td>
                      <td className="mono">${c.failure_cost.toFixed(2)}</td>
                      <td className="mono">${c.residual_expected_failure_cost.toFixed(2)}</td>
                      <td className="mono font-semibold">
                        ${c.total_expected_cost.toFixed(2)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[var(--text-faint)] text-[12px]">
            No intervention decisions recorded.
          </p>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel p-4 overflow-x-auto">
      <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)] mb-3">
        {title}
      </h2>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase text-[var(--text-faint)]">{label}</span>
      <span className="mono text-[13px]">{value}</span>
    </div>
  );
}
