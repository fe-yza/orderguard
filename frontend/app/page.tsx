"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
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
import { MarketplaceMap } from "@/components/MarketplaceMap";
import { InfoTooltip } from "@/components/tour/InfoTooltip";
import { useTour } from "@/lib/tour/TourContext";
import { TOUR_DEMO_CONFIG, TOUR_DEMO_SEED, TOUR_DEMO_THRESHOLD } from "@/lib/tour/steps";

const POLL_INTERVAL_MS = 20_000;
const DEFAULT_THRESHOLD = 50;
const FALLBACK_TOP_N = 10;
const THRESHOLD_PRESETS = [25, 50, 75];
const TOUR_MAP_STEP_IDS = ["marketplace-map-legend", "select-high-risk-order"];

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
  const tour = useTour();

  const [runs, setRuns] = useState<SimulationRunSummaryOut[] | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SimulationMetricsOut[] | null>(null);
  const [allRisk, setAllRisk] = useState<HighRiskOrderOut[] | null>(null);
  const [mapEntities, setMapEntities] = useState<MapEntitiesOut | null>(null);
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);

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
  }, [requestedRunId]);

  const refresh = useCallback((runId: string) => {
    // Fetch every scored order once (min_score=0), not just ones above the
    // current threshold — the threshold below is then a pure client-side
    // filter, so moving the slider never needs a round trip and the
    // fallback (showing top-N when nothing clears the bar) has real data
    // to fall back to instead of a second query.
    Promise.all([
      api.getSimulationMetrics(runId),
      api.getHighRiskOrders(runId, 0),
      api.getMapEntities(runId),
    ])
      .then(([m, risk, map]) => {
        setMetrics(m);
        setAllRisk(risk);
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

  // Guided-tour support: once the tour reaches the marketplace/high-risk
  // steps, it needs a real order to point at. Prefer the currently
  // selected run's own data; only fall back to a known-good demo scenario
  // (a real simulation config, re-run deterministically — never
  // fabricated) when this run genuinely has nothing above the threshold.
  useEffect(() => {
    if (!tour.active || !runs) return;
    if (tour.awaitedOrder) return;

    const noRunsYet = runs.length === 0;
    const onMapStep = tour.currentStep && TOUR_MAP_STEP_IDS.includes(tour.currentStep.id);
    // Kick off as soon as the tour starts if there's nothing to show at all
    // (a brand-new install), so the data is ready by the time the visitor
    // reaches the marketplace step instead of making them wait there.
    if (!noRunsYet && !onMapStep) return;

    if (!noRunsYet) {
      if (allRisk === null || !selectedRunId) return; // still loading current run's data
      const bestInCurrent = [...allRisk].sort(
        (a, b) =>
          b.latest_risk_assessment.overall_risk_score - a.latest_risk_assessment.overall_risk_score,
      )[0];
      if (
        bestInCurrent &&
        bestInCurrent.latest_risk_assessment.overall_risk_score >= TOUR_DEMO_THRESHOLD
      ) {
        tour.setAwaitedOrder({ runId: selectedRunId, orderId: bestInCurrent.order.id });
        return;
      }
    }

    let cancelled = false;
    (async () => {
      setBootstrapping(true);
      try {
        const demoRun = runs.find((r) => r.seed === TOUR_DEMO_SEED);
        if (demoRun) {
          const risk = await api.getHighRiskOrders(demoRun.id, TOUR_DEMO_THRESHOLD);
          if (risk.length > 0 && !cancelled) {
            setSelectedRunId(demoRun.id);
            tour.setAwaitedOrder({ runId: demoRun.id, orderId: risk[0].order.id });
            return;
          }
        }
        const response = await api.createExperiment(TOUR_DEMO_CONFIG, TOUR_DEMO_THRESHOLD);
        const risk = await api.getHighRiskOrders(response.simulation_run_id, TOUR_DEMO_THRESHOLD);
        const updatedRuns = await api.listSimulations();
        if (cancelled) return;
        setRuns(updatedRuns);
        setSelectedRunId(response.simulation_run_id);
        if (risk.length > 0) {
          tour.setAwaitedOrder({ runId: response.simulation_run_id, orderId: risk[0].order.id });
        }
      } catch (e) {
        if (!cancelled) setError(describeError(e));
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tour, runs, allRisk, selectedRunId]);

  const expectedValueMetrics = metrics?.find((m) => m.strategy === "expected_value");

  const aboveThreshold = useMemo(
    () => (allRisk ?? []).filter((r) => r.latest_risk_assessment.overall_risk_score >= threshold),
    [allRisk, threshold],
  );
  const usingFallback = allRisk !== null && allRisk.length > 0 && aboveThreshold.length === 0;
  const shownRisk = usingFallback ? allRisk.slice(0, FALLBACK_TOP_N) : aboveThreshold;

  const awaitingThisOrder =
    tour.active && tour.currentStep?.id === "select-high-risk-order" ? tour.awaitedOrder : null;
  const awaitedOrderDetail =
    awaitingThisOrder && awaitingThisOrder.runId === selectedRunId
      ? (allRisk ?? []).find((r) => r.order.id === awaitingThisOrder.orderId)
      : undefined;

  if (runs === null) {
    return (
      <div className="flex flex-col gap-5">
        <AboutBanner />
        <p className="text-[var(--text-dim)]">Loading…</p>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-col gap-5">
        <AboutBanner />
        {bootstrapping ? (
          <div className="panel p-6 max-w-lg text-[12px] text-[var(--text-dim)]">
            Setting up a demo scenario for the guided tour — running a real simulation now,
            typically a few seconds…
          </div>
        ) : (
          <div className="panel p-6 max-w-lg">
            <p className="text-[var(--text-dim)]">
              No simulations yet. Go to{" "}
              <Link href="/simulation-lab" className="text-[var(--accent)]">
                Simulation Lab
              </Link>{" "}
              to configure and run one — everything on this page is populated
              from that run&apos;s real output. Or{" "}
              <button className="text-[var(--accent)] underline" onClick={tour.startTour}>
                take the guided tour
              </button>{" "}
              and one will be set up for you automatically.
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <AboutBanner />

      <div data-tour="run-and-kpis" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
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
          <InfoTooltip title="What's a simulation run?">
            One complete synthetic marketplace scenario. The seed makes it reproducible — the
            same seed and settings always regenerate the exact same run.
          </InfoTooltip>
          <button
            className="panel px-3 py-1.5 text-[12px] hover:bg-[var(--bg-panel-raised)]"
            onClick={() => selectedRunId && refresh(selectedRunId)}
          >
            Refresh
          </button>
          <Link
            href="/simulation-lab"
            className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
          >
            Run new simulation
          </Link>
          {!tour.active ? (
            <button
              className="px-3 py-1.5 rounded-md text-[12px] font-medium"
              style={{ border: "1px solid var(--accent)", color: "var(--accent)" }}
              onClick={tour.startTour}
            >
              Take the guided tour
            </button>
          ) : null}
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
              value={String(aboveThreshold.length)}
              tone={aboveThreshold.length > 0 ? "warning" : "default"}
              sub={`score ≥ ${threshold}`}
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
      </div>

      {bootstrapping ? (
        <div className="panel p-3 text-[12px] text-[var(--text-dim)]">
          Setting up a demo scenario known to include high-risk deliveries — this run currently
          has none above the threshold, so a quick real simulation is being created for the
          tour…
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div data-tour="marketplace-map" className="panel p-3 lg:col-span-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)]">
              Marketplace map
            </h2>
            <span className="text-[11px] text-[var(--text-faint)]">
              synthetic coordinate plane — not a real map
            </span>
          </div>
          {mapEntities ? (
            <MarketplaceMap
              runId={selectedRunId!}
              merchants={mapEntities.merchants}
              drivers={mapEntities.drivers}
              customers={mapEntities.customers}
              deliveries={mapEntities.deliveries}
              highRiskThreshold={threshold}
              selectedOrderId={awaitingThisOrder?.orderId}
            />
          ) : (
            <div className="h-[420px] flex items-center justify-center text-[var(--text-faint)]">
              loading map…
            </div>
          )}
        </div>

        <div data-tour="high-risk-feed" className="panel p-3 lg:col-span-2 overflow-x-auto">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <h2 className="text-[12px] uppercase tracking-wide text-[var(--text-dim)]">
                High-risk order feed
              </h2>
              <InfoTooltip title="What's a risk score?">
                A 0-100 weighted score summarizing how concerning a delivery looks based on
                observable conditions — not a calibrated probability of failure.
              </InfoTooltip>
            </div>
            <div className="flex items-center gap-1 text-[11px]">
              <span className="text-[var(--text-faint)]">risk ≥</span>
              {THRESHOLD_PRESETS.map((t) => (
                <button
                  key={t}
                  onClick={() => setThreshold(t)}
                  className={`px-1.5 py-0.5 rounded ${
                    threshold === t
                      ? "bg-[var(--accent)] text-black"
                      : "bg-[var(--bg-panel-raised)] text-[var(--text-dim)]"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {awaitedOrderDetail ? (
            <div
              className="mb-3 p-2.5 rounded-md flex items-center justify-between gap-2"
              style={{ border: "2px solid var(--accent)", background: "var(--bg-panel-raised)" }}
            >
              <div className="text-[12px]">
                <span className="mono">{awaitedOrderDetail.order.id}</span> · risk{" "}
                <span className="mono text-[var(--danger)]">
                  {awaitedOrderDetail.latest_risk_assessment.overall_risk_score.toFixed(1)}
                </span>{" "}
                · predicted {awaitedOrderDetail.latest_risk_assessment.predicted_failure_type ?? "—"}
              </div>
              <Link
                href={`/simulations/${awaitingThisOrder!.runId}/orders/${awaitingThisOrder!.orderId}`}
                className="px-3 py-1 rounded-md bg-[var(--accent)] text-black text-[11px] font-medium whitespace-nowrap"
              >
                Open this delivery →
              </Link>
            </div>
          ) : null}

          {allRisk === null ? (
            <p className="text-[var(--text-faint)] text-[12px]">loading…</p>
          ) : allRisk.length === 0 ? (
            <p className="text-[var(--text-faint)] text-[12px]">
              This run has no scored orders yet.
            </p>
          ) : (
            <>
              {usingFallback ? (
                <p className="text-[11px] text-[var(--warning)] mb-2">
                  No orders in this run scored ≥ {threshold} — showing the {shownRisk.length}{" "}
                  highest-risk orders instead (all below the threshold, so this run was a
                  relatively healthy one).
                </p>
              ) : null}
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Status</th>
                    <th>Risk</th>
                    <th>Predicted</th>
                    <th>Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {shownRisk.map(({ order, latest_risk_assessment }) => (
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
                      <td
                        className="mono"
                        style={{
                          color:
                            latest_risk_assessment.overall_risk_score >= threshold
                              ? "var(--danger)"
                              : undefined,
                        }}
                      >
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function AboutBanner() {
  return (
    <div data-tour="about-banner" className="panel px-4 py-2.5 text-[12px] text-[var(--text-dim)]">
      <span className="text-[var(--text)] font-medium">OrderGuard</span> predicts delivery
      failure risk and evaluates cost-justified interventions in a synthetic on-demand delivery
      marketplace simulation. <InfoTooltip title="Why synthetic data?">
        There&apos;s no real delivery marketplace to use, so this project simulates its own —
        with realistic causal structure — to test the prediction and intervention system
        end-to-end.
      </InfoTooltip>{" "}
      <span className="text-[var(--text-faint)]">
        All data on this page is generated by a seeded simulation run in this repo — no real
        company, courier, or customer data (DoorDash or otherwise) is used anywhere.
      </span>
    </div>
  );
}

function describeError(e: unknown): string {
  if (e instanceof ApiError) return `API error ${e.status}: ${e.message}`;
  if (e instanceof Error) return e.message;
  return "Unknown error";
}
