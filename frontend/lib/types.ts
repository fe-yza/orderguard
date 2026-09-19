// Mirrors backend/src/orderguard/api/schemas.py. Kept as plain interfaces,
// not generated, since the API surface is still small and actively
// changing — codegen would be premature here.

export interface RushHourWindowIn {
  start_minute: number;
  end_minute: number;
  demand_multiplier: number;
  speed_multiplier: number;
}

export interface SimulationConfigIn {
  seed: number;
  start_time: string;
  duration_minutes: number;
  num_merchants: number;
  num_drivers: number;
  num_customers: number;
  base_order_rate_per_minute: number;
  map_size_km: number;
  avg_driver_speed_kmh?: number;
  driver_offline_probability_per_tick?: number;
  merchant_stockout_probability?: number;
  customer_unreachable_probability?: number;
  perishable_spoilage_probability_per_tick?: number;
  rush_hour_windows?: RushHourWindowIn[];
}

export interface SimulationMetricsOut {
  strategy: "no_intervention" | "threshold_based" | "expected_value";
  total_orders: number;
  delivered_count: number;
  failed_count: number;
  cancelled_count: number;
  in_flight_count: number;
  late_delivered_count: number;
  late_rate: number;
  failure_rate: number;
  cancellation_rate: number;
  avg_delay_minutes: number;
  p50_delay_minutes: number;
  p95_delay_minutes: number;
  intervention_count: number;
  intervention_rate: number;
  total_intervention_cost: number;
  failure_reason_counts: Record<string, number>;
  cancellation_reason_counts: Record<string, number>;
}

export interface ExperimentResponseOut {
  simulation_run_id: string;
  threshold_used: number;
  metrics: SimulationMetricsOut[];
}

export interface SimulationRunSummaryOut {
  id: string;
  seed: number;
  started_at: string;
  completed_at: string;
  created_at: string;
}

export interface OrderSummaryOut {
  id: string;
  merchant_id: string;
  customer_id: string;
  status: string;
  is_perishable: boolean;
  created_at: string;
  promised_delivery_time: string;
  delivered_at: string | null;
  cancellation_reason: string | null;
  failure_reason: string | null;
}

export interface RiskFactorOut {
  name: string;
  description: string;
  weight: number;
  raw_signal: number;
  contribution: number;
}

export interface RiskAssessmentOut {
  id: string;
  computed_at: string;
  overall_risk_score: number;
  predicted_failure_type: string | null;
  confidence: number;
  predicted_delay_minutes: number;
  factors: RiskFactorOut[];
}

export interface InterventionCandidateOut {
  intervention_type: string;
  direct_cost: number;
  failure_probability: number;
  failure_cost: number;
  probability_reduction: number;
  cost_reduction_fraction: number;
  residual_expected_failure_cost: number;
  total_expected_cost: number;
}

export interface InterventionDecisionOut {
  id: string;
  computed_at: string;
  chosen: string;
  rationale: string;
  candidates: InterventionCandidateOut[];
}

export interface DeliveryEventOut {
  event_type: string;
  occurred_at: string;
  details: Record<string, unknown>;
}

export interface OrderDetailOut extends OrderSummaryOut {
  events: DeliveryEventOut[];
  risk_assessments: RiskAssessmentOut[];
  intervention_decisions: InterventionDecisionOut[];
}

export interface HighRiskOrderOut {
  order: OrderSummaryOut;
  latest_risk_assessment: RiskAssessmentOut;
}

export interface MerchantOut {
  id: string;
  name: string;
  location_x_km: number;
  location_y_km: number;
  reliability_score: number;
  final_backlog: number;
}

export interface DriverOut {
  id: string;
  name: string;
  location_x_km: number;
  location_y_km: number;
  reliability_score: number;
  final_status: string;
}

export interface CustomerOut {
  id: string;
  name: string;
  location_x_km: number;
  location_y_km: number;
  reachability_score: number;
}

export interface MapEntitiesOut {
  merchants: MerchantOut[];
  drivers: DriverOut[];
  customers: CustomerOut[];
}
