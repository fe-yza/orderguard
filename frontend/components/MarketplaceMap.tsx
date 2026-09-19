"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import type { CustomerOut, DriverOut, MapDeliveryOut, MerchantOut } from "@/lib/types";

const MAX_ROUTES_RENDERED = 900;

const DRIVER_COLOR: Record<string, string> = {
  available: "#4cbb7d",
  offline: "#5b6270",
};
const DRIVER_COLOR_DEFAULT = "#5b9dff"; // en_route / waiting / delivering

function terminalRouteColor(status: string): string {
  if (status === "delivered") return "#4cbb7d";
  if (status === "failed") return "#ef5a5a";
  return "#5b6270"; // cancelled
}

export function MarketplaceMap({
  runId,
  merchants,
  drivers,
  customers,
  deliveries,
  highRiskThreshold,
  selectedOrderId,
}: {
  runId: string;
  merchants: MerchantOut[];
  drivers: DriverOut[];
  customers: CustomerOut[];
  deliveries: MapDeliveryOut[];
  highRiskThreshold: number;
  selectedOrderId?: string | null;
}) {
  const router = useRouter();

  const bounds = useMemo(() => {
    const xs = [
      ...merchants.map((m) => m.location_x_km),
      ...drivers.map((d) => d.location_x_km),
      ...customers.map((c) => c.location_x_km),
    ];
    const ys = [
      ...merchants.map((m) => m.location_y_km),
      ...drivers.map((d) => d.location_y_km),
      ...customers.map((c) => c.location_y_km),
    ];
    if (xs.length === 0) return { minX: 0, minY: 0, w: 1, h: 1, unit: 1 };
    const minXRaw = Math.min(...xs);
    const maxXRaw = Math.max(...xs);
    const minYRaw = Math.min(...ys);
    const maxYRaw = Math.max(...ys);
    const spanX = Math.max(maxXRaw - minXRaw, 0.1);
    const spanY = Math.max(maxYRaw - minYRaw, 0.1);
    const pad = Math.max(spanX, spanY) * 0.08;
    const w = spanX + pad * 2;
    const h = spanY + pad * 2;
    return { minX: minXRaw - pad, minY: minYRaw - pad, w, h, unit: Math.max(w, h) };
  }, [merchants, drivers, customers]);

  const routedDeliveries = useMemo(() => {
    const withDriver = deliveries.filter((d) => d.driver_id !== null);
    if (withDriver.length <= MAX_ROUTES_RENDERED) return withDriver;
    // Deterministic downsample (every Nth), not random — a demo should show
    // the same subset on every render, not flicker between reloads.
    const stride = Math.ceil(withDriver.length / MAX_ROUTES_RENDERED);
    return withDriver.filter((_, i) => i % stride === 0);
  }, [deliveries]);

  const truncated = routedDeliveries.length < deliveries.filter((d) => d.driver_id !== null).length;

  const r = bounds.unit * 0.012;
  const merchantSize = bounds.unit * 0.02;

  return (
    <div>
      <svg
        viewBox={`${bounds.minX} ${bounds.minY} ${bounds.w} ${bounds.h}`}
        className="w-full h-[420px] rounded-md border border-[var(--border)]"
        style={{ background: "var(--bg)" }}
      >
        {/* delivery routes, drawn first so markers sit on top */}
        {routedDeliveries.map((d) => {
          const isActive = d.is_active;
          const isHighRisk =
            isActive && d.latest_risk_score !== null && d.latest_risk_score >= highRiskThreshold;
          const color = isActive
            ? isHighRisk
              ? "#ef5a5a"
              : "#5b9dff"
            : terminalRouteColor(d.status);
          const opacity = isActive ? (isHighRisk ? 0.95 : 0.55) : 0.22;
          const width = isHighRisk ? r * 0.55 : r * 0.22;
          const isSelected = selectedOrderId === d.order_id;

          return (
            <g
              key={d.order_id}
              className="cursor-pointer"
              onClick={() => router.push(`/simulations/${runId}/orders/${d.order_id}`)}
            >
              <title>
                {d.order_id} · {d.status}
                {d.latest_risk_score !== null ? ` · risk ${d.latest_risk_score.toFixed(0)}` : ""}
                {d.predicted_failure_type ? ` · predicted: ${d.predicted_failure_type}` : ""}
              </title>
              {/* invisible wide hit-area for easier clicking */}
              <line
                x1={d.merchant_x_km}
                y1={d.merchant_y_km}
                x2={d.customer_x_km}
                y2={d.customer_y_km}
                stroke="transparent"
                strokeWidth={r * 1.2}
              />
              <line
                x1={d.merchant_x_km}
                y1={d.merchant_y_km}
                x2={d.customer_x_km}
                y2={d.customer_y_km}
                stroke={color}
                strokeWidth={isSelected ? width * 2.2 : width}
                opacity={isSelected ? 1 : opacity}
              />
              <circle
                cx={d.customer_x_km}
                cy={d.customer_y_km}
                r={r * 0.4}
                className="fill-[var(--text-faint)]"
                opacity={0.5}
              />
              {isActive && d.driver_x_km !== null && d.driver_y_km !== null ? (
                <circle
                  cx={d.driver_x_km}
                  cy={d.driver_y_km}
                  r={isHighRisk ? r * 0.9 : r * 0.65}
                  fill={
                    d.driver_status ? DRIVER_COLOR[d.driver_status] ?? DRIVER_COLOR_DEFAULT : DRIVER_COLOR_DEFAULT
                  }
                  stroke={isHighRisk ? "#ef5a5a" : "none"}
                  strokeWidth={isHighRisk ? r * 0.15 : 0}
                />
              ) : null}
            </g>
          );
        })}

        {/* merchants: fixed reference points, always shown */}
        {merchants.map((m) => (
          <rect
            key={m.id}
            x={m.location_x_km - merchantSize / 2}
            y={m.location_y_km - merchantSize / 2}
            width={merchantSize}
            height={merchantSize}
            className="fill-[var(--warning)]"
          >
            <title>
              {m.id} · reliability {(m.reliability_score * 100).toFixed(0)}% · backlog{" "}
              {m.final_backlog}
            </title>
          </rect>
        ))}

        {/* idle/available drivers not currently on a visualized route */}
        {drivers
          .filter((d) => d.final_status === "available" || d.final_status === "offline")
          .map((d) => (
            <circle
              key={d.id}
              cx={d.location_x_km}
              cy={d.location_y_km}
              r={r * 0.5}
              fill={DRIVER_COLOR[d.final_status] ?? DRIVER_COLOR_DEFAULT}
              opacity={d.final_status === "offline" ? 0.35 : 0.85}
            >
              <title>
                {d.id} · {d.final_status} · reliability {(d.reliability_score * 100).toFixed(0)}%
              </title>
            </circle>
          ))}
      </svg>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-[10px] text-[var(--text-dim)]">
        <LegendItem color="var(--warning)" shape="square" label="Merchant" />
        <LegendItem color="#4cbb7d" shape="circle" label="Driver (available)" />
        <LegendItem color="#5b6270" shape="circle" label="Driver (offline)" />
        <LegendItem color="#5b9dff" shape="line" label="Active delivery" />
        <LegendItem color="#ef5a5a" shape="line" label="Active · high risk" />
        <LegendItem color="#4cbb7d" shape="line" label="Resolved · delivered" opacity={0.4} />
        <LegendItem color="#ef5a5a" shape="line" label="Resolved · failed" opacity={0.4} />
        {truncated ? (
          <span className="text-[var(--text-faint)]">
            showing {routedDeliveries.length} of{" "}
            {deliveries.filter((d) => d.driver_id !== null).length} routed deliveries
          </span>
        ) : null}
      </div>
    </div>
  );
}

function LegendItem({
  color,
  shape,
  label,
  opacity = 1,
}: {
  color: string;
  shape: "square" | "circle" | "line";
  label: string;
  opacity?: number;
}) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width="12" height="12" viewBox="0 0 12 12" style={{ opacity }}>
        {shape === "square" ? <rect x="2" y="2" width="8" height="8" fill={color} /> : null}
        {shape === "circle" ? <circle cx="6" cy="6" r="4" fill={color} /> : null}
        {shape === "line" ? (
          <line x1="0" y1="6" x2="12" y2="6" stroke={color} strokeWidth="2.5" />
        ) : null}
      </svg>
      {label}
    </span>
  );
}
