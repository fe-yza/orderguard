"use client";

import { useTour } from "@/lib/tour/TourContext";

export function IntroModal() {
  const tour = useTour();
  if (!tour.showIntroModal) return null;

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
      }}
    >
      <div className="panel p-6" style={{ maxWidth: 480, border: "1px solid var(--border)" }}>
        <span className="text-[10px] uppercase tracking-wide text-[var(--accent)]">
          ~2 minute tour
        </span>
        <h2 className="text-[16px] font-semibold mt-1 mb-3">Welcome to OrderGuard</h2>
        <p className="text-[13px] text-[var(--text-dim)] leading-relaxed mb-3">
          OrderGuard predicts delivery failure risk and decides when intervention is
          economically worthwhile in a synthetic on-demand delivery marketplace.
        </p>
        <p className="text-[13px] text-[var(--text-dim)] leading-relaxed mb-3">
          This project does not use DoorDash, Uber, or any real company&apos;s data. It contains
          its own simulated delivery marketplace so the prediction and intervention system can be
          tested end-to-end.
        </p>
        <p className="text-[13px] text-[var(--text-dim)] leading-relaxed mb-5">
          During this tour, you&apos;ll follow an order through the marketplace, see how
          OrderGuard identifies risk, inspect why the order is risky, see how it evaluates
          interventions, and run an experiment comparing different decision strategies.
        </p>
        <div className="flex gap-2">
          <button
            className="px-4 py-2 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
            onClick={tour.startTour}
          >
            Start guided tour
          </button>
          <button
            className="px-4 py-2 rounded-md bg-[var(--bg-panel-raised)] text-[var(--text-dim)] text-[12px]"
            onClick={tour.dismissIntro}
          >
            Explore on my own
          </button>
        </div>
      </div>
    </div>
  );
}
