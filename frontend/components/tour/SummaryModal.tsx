"use client";

import { useTour } from "@/lib/tour/TourContext";

const REAL: string[] = [
  "Domain model & simulation engine",
  "Event system",
  "Risk engine",
  "Intervention engine",
  "Experiment framework",
  "PostgreSQL persistence",
  "FastAPI API",
  "Frontend / dashboard",
  "Tests",
  "Docker / CI",
];

const SIMULATED: string[] = [
  "Marketplace data (merchants, drivers, customers)",
  "Delivery events",
  "Failure hazards",
  "Intervention cost / effect assumptions",
];

export function SummaryModal() {
  const tour = useTour();
  if (!tour.showSummaryModal) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10050,
        background: "rgba(5,7,9,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        overflowY: "auto",
      }}
    >
      <div className="panel p-6" style={{ maxWidth: 540, border: "1px solid var(--border)" }}>
        <h2 className="text-[16px] font-semibold mb-3">You&apos;ve completed the OrderGuard demo</h2>
        <p className="text-[13px] text-[var(--text-dim)] leading-relaxed mb-3">
          You just followed the complete OrderGuard pipeline:
        </p>
        <ol className="text-[12px] text-[var(--text-dim)] leading-relaxed mb-4 list-decimal pl-4 flex flex-col gap-1">
          <li>A synthetic marketplace generated delivery activity.</li>
          <li>OrderGuard observed delivery state and events.</li>
          <li>The risk engine identified deliveries showing warning signals.</li>
          <li>The intervention engine evaluated whether acting was economically worthwhile.</li>
          <li>The simulation produced actual synthetic outcomes.</li>
          <li>The experiment framework compared OrderGuard with simpler strategies.</li>
          <li>The dashboard exposed the resulting data through the application.</li>
        </ol>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <h3 className="text-[10px] uppercase tracking-wide text-[var(--success)] mb-1.5">
              Real implementation
            </h3>
            <ul className="text-[11px] text-[var(--text-dim)] flex flex-col gap-1">
              {REAL.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-[10px] uppercase tracking-wide text-[var(--warning)] mb-1.5">
              Simulated / assumed
            </h3>
            <ul className="text-[11px] text-[var(--text-dim)] flex flex-col gap-1">
              {SIMULATED.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>

        <p className="text-[12px] text-[var(--text-faint)] leading-relaxed mb-5">
          OrderGuard is an engineering demonstration, not a production model trained on
          proprietary delivery-company data.
        </p>

        <div className="flex gap-2">
          <button
            className="px-4 py-2 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
            onClick={tour.closeSummary}
          >
            Explore OrderGuard
          </button>
          <button
            className="px-4 py-2 rounded-md bg-[var(--bg-panel-raised)] text-[var(--text-dim)] text-[12px]"
            onClick={tour.restartTour}
          >
            Restart tour
          </button>
        </div>
      </div>
    </div>
  );
}
