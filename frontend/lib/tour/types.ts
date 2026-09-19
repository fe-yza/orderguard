export type TourPage = "/" | "/simulation-lab" | "order-detail";

export type TourAdvance =
  | { type: "manual" } // Next button
  | { type: "click-order" } // advance when the visitor opens the target order
  | { type: "run-experiment" }; // advance when a POST /simulations succeeds

export interface TourRuntimeFacts {
  /** Does the currently-open order have more than one risk assessment
   * (i.e. does the risk-over-time chart section actually exist)? */
  orderHasRiskHistory: boolean;
}

export interface TourStep {
  id: string;
  page: TourPage;
  /** CSS selector (via [data-tour="..."]) for the element to spotlight. */
  target: string;
  title: string;
  /** Plain strings render as paragraphs; keep each one short. */
  body: string[];
  advance: TourAdvance;
  /** Shown only for advance.type === "manual". Defaults to "Next". */
  nextLabel?: string;
  /** Evaluated right before showing this step; if true, it's skipped
   * (used when a step's target section only conditionally exists — e.g.
   * an order with a single risk assessment has no history chart to show). */
  skipIf?: (facts: TourRuntimeFacts) => boolean;
}
