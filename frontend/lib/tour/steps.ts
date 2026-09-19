import type { TourStep } from "./types";

// Copy here is checked against the actual implementation (risk/engine.py,
// interventions/engine.py, experiments/runner.py, experiments/policies.py)
// as of the guided-tour feature — see docs/interview-notes.md for the full
// accuracy audit. Nothing below claims more precision than the code has:
// risk score is a weighted-average heuristic (0-100), not a calibrated
// probability; confidence is a heuristic based on how much observable
// signal fed the assessment, not a statistical confidence interval.

export const TOUR_STEPS: TourStep[] = [
  {
    id: "intro-flow",
    page: "/",
    target: '[data-tour="about-banner"]',
    title: "Meet OrderGuard",
    body: [
      "OrderGuard is a delivery-risk prediction and intervention system running on a synthetic on-demand delivery marketplace.",
      "As simulated orders move from merchants to customers, OrderGuard observes their state and estimates whether each delivery is becoming likely to fail or arrive late.",
      "When risk increases, OrderGuard can evaluate possible interventions — but intervention costs money, so the system must decide whether acting is actually worth it.",
      "Marketplace → Events → Risk prediction → Intervention decision → Outcome.",
      "The marketplace is simulated, but the architecture around it is real: events flow through the system, risk is calculated, decisions are made, results are persisted, APIs expose them, and this dashboard visualizes them.",
    ],
    advance: { type: "manual" },
    nextLabel: "Show me the marketplace",
  },
  {
    id: "overview-kpis",
    page: "/",
    target: '[data-tour="run-and-kpis"]',
    title: "Reading the Overview",
    body: [
      "A simulation run is one complete synthetic marketplace scenario — the dropdown above lets you pick which run's data this page shows. The seed makes a scenario reproducible: the same seed and settings always regenerate the exact same run.",
      "Active Deliveries: orders currently moving through the delivery lifecycle in this run.",
      "High-Risk Orders: active orders whose current risk score is at or above the threshold selected in the feed on the right.",
      "Failure Rate: the share of all orders in this run that ended in a terminal failure (not cancelled, not still delivered — actually failed).",
      "Interventions Triggered / Cost: how many times OrderGuard's expected-value strategy chose to act on this run, and what that cost in total.",
      "Late Rate: of the orders that were successfully delivered, the share that arrived after their promised time.",
      "All of these numbers belong to whichever run is selected above — switch runs and they change.",
    ],
    advance: { type: "manual" },
    nextLabel: "Next: see the marketplace",
  },
  {
    id: "marketplace-map-legend",
    page: "/",
    target: '[data-tour="marketplace-map"]',
    title: "The marketplace map",
    body: [
      "This is not a geographic map — it's a synthetic coordinate plane. Amber squares are merchants. Circles are drivers: green means available, gray means offline, and drivers actively delivering appear along a route line.",
      "Lines are delivery routes from merchant to customer. Blue means an active delivery at normal risk; red means active and at or above the risk threshold. Faded green/red/gray lines are already-resolved deliveries (delivered, failed, or cancelled).",
      "Each delivery changes state as the simulation progresses. Importantly, the risk engine evaluates observable delivery conditions — merchant backlog, driver reliability, how the promised time compares to projected completion — not the simulator's hidden failure probabilities. It has to infer risk the way a real ops system would, not read the answer key.",
    ],
    advance: { type: "manual" },
    nextLabel: "Next: find a risky delivery",
  },
  {
    id: "select-high-risk-order",
    page: "/",
    target: '[data-tour="high-risk-feed"]',
    title: "Find a high-risk delivery",
    body: [
      "The order below is currently at or above the risk threshold — it's also highlighted in red on the map.",
      "Click this button to continue.",
    ],
    advance: { type: "click-order" },
  },
  {
    id: "order-status",
    page: "order-detail",
    target: '[data-tour="order-header"]',
    title: "One individual delivery",
    body: [
      "Now we're looking at a single order end to end: its current status, whether it's perishable, and — if it already failed or was cancelled — exactly why.",
      "Everything on this page traces back to real events this specific order generated during the simulation.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "order-timeline",
    page: "order-detail",
    target: '[data-tour="order-timeline"]',
    title: "The timeline — measured, not modeled",
    body: [
      "This is the order's actual event history: every state change the simulation recorded, in order, with a timestamp. Marked \"measured\" because it's a direct log of what happened, not a prediction.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "order-risk",
    page: "order-detail",
    target: '[data-tour="risk-assessment"]',
    title: "The risk score",
    body: [
      "The risk score (0-100) summarizes how concerning this delivery looks right now, based on observable conditions like projected lateness, merchant backlog, and driver/customer reliability. It's a weighted score, not a calibrated probability of failure.",
      "\"Predicted\" is the most likely way this order fails if nothing changes, inferred from whichever signal is contributing the most — it only appears once the score clears a minimum bar. \"Confidence\" reflects how much observable signal fed the assessment (more relevant signals available → higher stated confidence) — it is not a statistical probability either.",
      "The factors table below breaks the score into pieces: each factor's weight (its maximum possible contribution), its raw signal (0-1, how strongly it fired), and its actual contribution. This is what makes the number explainable instead of a black box.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "order-risk-history",
    page: "order-detail",
    target: '[data-tour="risk-history-chart"]',
    title: "Risk changes over time",
    body: [
      "This chart plots every risk assessment ever computed for this order. OrderGuard recomputes risk when something happens to an order (a new event on the event bus), not on a fixed timer — so a flat stretch means nothing new happened in that gap, not that risk was reassessed and stayed put.",
    ],
    advance: { type: "manual" },
    skipIf: (facts) => !facts.orderHasRiskHistory,
  },
  {
    id: "intervention-decision",
    page: "order-detail",
    target: '[data-tour="intervention-section"]',
    title: "Should OrderGuard intervene?",
    body: [
      "Detecting risk is only half the problem. An intervention (notifying the customer, reassigning the driver, offering a credit, etc.) can reduce the chance or the cost of failure — but every intervention costs something. Acting on every risky order could waste more money than it saves.",
      "Expected net value = (cost of doing nothing) − (direct cost + residual expected failure cost of acting). OrderGuard computes this for every applicable action — including doing nothing — and picks whichever number is lowest.",
      "\"Est. prob. reduction\" and \"est. cost reduction\" are configured modeling assumptions about how well each lever works, not values learned from real outcome data (there is no real marketplace to learn them from — this project says so explicitly rather than implying otherwise). The highlighted row is the one actually chosen.",
    ],
    advance: { type: "manual" },
    nextLabel: "But does this strategy actually help?",
  },
  {
    id: "why-experiments",
    page: "order-detail",
    target: '[data-tour="intervention-section"]',
    title: "Why we need experiments",
    body: [
      "One successful-looking decision doesn't prove a strategy works. To evaluate OrderGuard, the same synthetic marketplace conditions are run under different intervention strategies and the outcomes are compared.",
      "No intervention: the system observes deliveries but never acts.",
      "Threshold-based: a simple baseline — the same one fixed action, triggered whenever risk crosses a fixed number, regardless of cause or cost.",
      "OrderGuard (expected-value): the cost-aware strategy from the last screen — it only acts when the expected benefit justifies the cost, and picks from the full catalog of actions.",
    ],
    advance: { type: "manual" },
    nextLabel: "Open Simulation Lab",
  },
  {
    id: "sim-lab-intro",
    page: "/simulation-lab",
    target: '[data-tour="sim-config-scale"]',
    title: "Simulation Lab",
    body: [
      "This is where you configure the conditions of the synthetic marketplace — how many merchants and drivers, how fast orders arrive, how long the scenario runs — and compare how the three strategies behave under the same conditions.",
      "Every field here maps directly to a real parameter the simulation engine accepts; nothing is decorative.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "sim-lab-hazards",
    page: "/simulation-lab",
    target: '[data-tour="hazard-rates"]',
    title: "Ground truth vs. what the risk engine sees",
    body: [
      "These four numbers control how often things actually go wrong inside the simulator — the hidden ground truth used to generate outcomes. OrderGuard's risk engine never receives these values; it only ever sees observable state (backlog, elapsed time, reliability scores), the same way a real system would have to infer risk without reading the answer key.",
      "Driver goes offline and perishable spoilage are checked every simulated minute while they're relevant (a driver mid-delivery; a perishable order already running late). Merchant stockout and customer unreachable are each checked once — at order confirmation and at arrival, respectively.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "sim-lab-threshold",
    page: "/simulation-lab",
    target: '[data-tour="baseline-threshold"]',
    title: "The baseline's threshold",
    body: [
      "This number belongs only to the simple threshold-based comparison strategy from the last screen. OrderGuard's own expected-value strategy doesn't use a fixed threshold at all — it evaluates cost vs. benefit for every order individually.",
    ],
    advance: { type: "manual" },
  },
  {
    id: "run-experiment",
    page: "/simulation-lab",
    target: '[data-tour="run-button"]',
    title: "Run an experiment",
    body: [
      "Click this button to continue.",
      "Behind the scenes: OrderGuard generates one seeded synthetic marketplace, then runs it three separate times — once per strategy, from the same starting conditions — processing every delivery event, evaluating risk and intervention decisions as they happen, persisting the results, and computing comparable outcome metrics.",
      "This takes a few seconds for a moderate-sized scenario.",
    ],
    advance: { type: "run-experiment" },
  },
  {
    id: "read-results",
    page: "/simulation-lab",
    target: '[data-tour="results-section"]',
    title: "Reading the results",
    body: [
      "The chart compares the three strategies under the same simulated conditions — lower bars are better for all three metrics shown.",
      "Orders / Delivered / Failed / Cancelled are raw counts for that strategy's run. Late rate is the share of delivered orders that arrived after their promised time; failure rate is the share of all orders that ended in a terminal failure.",
      "\"Avg delay\" and \"P95 delay\" measure how far delivery time missed the promised time, in minutes, averaged only over delivered orders. Negative means early, positive means late — a −20 average means deliveries in that run finished about 20 minutes ahead of schedule on average. P95 is the delay that 95% of delivered orders did better than — a way to see the bad tail without one outlier skewing an average.",
      "Interventions / Cost show how many times that strategy acted and what it spent. These numbers are never adjusted to favor any strategy — expected-value can and sometimes does perform about the same as, or worse than, a baseline in a given run.",
    ],
    advance: { type: "manual" },
    nextLabel: "Finish tour",
  },
];

export const TOUR_DEMO_SEED = 21;

/**
 * A config verified (by hand, against the real backend) to reliably
 * produce several genuinely high-risk orders — used only as a fallback so
 * the tour never gets stuck on a run that happens to be "healthy." Same
 * seed always regenerates the exact same scenario; this is a real
 * simulation config, not fabricated data.
 */
export const TOUR_DEMO_CONFIG = {
  seed: TOUR_DEMO_SEED,
  start_time: "2026-01-01T08:00:00",
  duration_minutes: 240,
  num_merchants: 10,
  num_drivers: 12,
  num_customers: 150,
  base_order_rate_per_minute: 1.4,
  map_size_km: 14.0,
  promised_delivery_buffer_minutes: 8.0,
  avg_merchant_prep_minutes: 18.0,
  merchant_prep_stddev_minutes: 6.0,
  rush_hour_windows: [
    { start_minute: 0, end_minute: 240, demand_multiplier: 2.0, speed_multiplier: 0.45 },
  ],
};

export const TOUR_DEMO_THRESHOLD = 50;
