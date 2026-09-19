"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTour } from "@/lib/tour/TourContext";
import { useTourTarget } from "@/lib/tour/useTourTarget";
import { computeCardPosition } from "@/lib/tour/placement";

const Z_FRAME = 9998;
const Z_SPOTLIGHT = 9999;
const Z_CARD = 10000;

export function TourOverlay() {
  const tour = useTour();
  const { active, currentStep, currentIndex, totalSteps, onExpectedPage, expectedPath } = tour;
  const { rect } = useTourTarget(active ? currentStep?.target ?? null : null);

  const cardRef = useRef<HTMLDivElement>(null);
  const [cardSize, setCardSize] = useState({ width: 340, height: 200 });
  const [viewport, setViewport] = useState({ width: 1200, height: 800 });

  useEffect(() => {
    const sync = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  useLayoutEffect(() => {
    if (cardRef.current) {
      const r = cardRef.current.getBoundingClientRect();
      setCardSize({ width: r.width, height: r.height });
    }
  }, [currentStep, rect]);

  useEffect(() => {
    if (!active || !onExpectedPage) return;
    const el = document.querySelector(currentStep?.target ?? "");
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [active, currentStep, onExpectedPage]);

  // Normal step transitions (especially cross-page navigation) have a
  // brief window where the target legitimately hasn't rendered yet — data
  // still loading, page still mounting. Only treat it as "stuck" if that
  // persists a bit, so this never flashes during an ordinary transition.
  // This gates when to show a fallback UI, not whether/when the tour
  // advances — it never substitutes for the real click/success events.
  const [showStuck, setShowStuck] = useState(false);
  /* eslint-disable react-hooks/set-state-in-effect -- debounce timer:
     resetting the flag when the target/step changes, then arming a
     settle-timer, is the whole point of this effect (syncing to a timer,
     an external clock), not a computation that belongs in render. */
  useEffect(() => {
    setShowStuck(false);
    if (rect) return;
    const t = setTimeout(() => setShowStuck(true), 1500);
    return () => clearTimeout(t);
  }, [rect, currentStep]);
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!active || !currentStep) return null;

  // Off-script: the visitor navigated somewhere the current step doesn't
  // expect, or the target genuinely isn't on the page (e.g. a hard refresh
  // wiped this page's in-memory state, like a Simulation Lab result).
  // Never leave them guessing what to do — offer one clear way forward,
  // and don't offer "Resume" when resuming would just loop back here.
  if (!onExpectedPage || (!rect && showStuck)) {
    const canResume = !onExpectedPage && expectedPath !== null;
    return (
      <div style={{ position: "fixed", inset: 0, zIndex: Z_CARD, pointerEvents: "none" }}>
        <div
          className="panel p-4"
          style={{
            position: "fixed",
            bottom: 20,
            right: 20,
            width: 320,
            pointerEvents: "auto",
            border: "1px solid var(--accent)",
          }}
        >
          <p className="text-[12px] text-[var(--text)] mb-2">
            {canResume
              ? "The guided tour is paused — this isn't the screen it expects right now."
              : "This step's content isn't available right now (a page refresh may have reset it)."}
          </p>
          <div className="flex gap-2">
            {canResume ? (
              <button
                className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
                onClick={() => (window.location.href = expectedPath!)}
              >
                Resume tour
              </button>
            ) : (
              <button
                className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
                onClick={tour.restartTour}
              >
                Restart tour
              </button>
            )}
            <button
              className="px-3 py-1.5 rounded-md bg-[var(--bg-panel-raised)] text-[var(--text-dim)] text-[12px]"
              onClick={tour.exitTour}
            >
              Exit tour
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!rect) return null; // within the grace period — render nothing yet

  const cardPos = computeCardPosition(rect, cardSize.width, cardSize.height, viewport.width, viewport.height);
  const showNext = currentStep.advance.type === "manual";

  return (
    <>
      {/* four click-blocking dimmed frames around the spotlight rect */}
      <div style={frameStyle({ top: 0, left: 0, width: viewport.width, height: Math.max(0, rect.top) })} />
      <div
        style={frameStyle({
          top: rect.bottom,
          left: 0,
          width: viewport.width,
          height: Math.max(0, viewport.height - rect.bottom),
        })}
      />
      <div
        style={frameStyle({ top: rect.top, left: 0, width: Math.max(0, rect.left), height: rect.height })}
      />
      <div
        style={frameStyle({
          top: rect.top,
          left: rect.right,
          width: Math.max(0, viewport.width - rect.right),
          height: rect.height,
        })}
      />

      {/* decorative spotlight border, no pointer interception */}
      <div
        style={{
          position: "fixed",
          top: rect.top - 3,
          left: rect.left - 3,
          width: rect.width + 6,
          height: rect.height + 6,
          border: "2px solid var(--accent)",
          borderRadius: 8,
          boxShadow: "0 0 0 3px rgba(91,157,255,0.25)",
          zIndex: Z_SPOTLIGHT,
          pointerEvents: "none",
          transition: "top 160ms ease, left 160ms ease, width 160ms ease, height 160ms ease",
        }}
      />

      <div
        ref={cardRef}
        className="panel p-4"
        style={{
          position: "fixed",
          top: cardPos.top,
          left: cardPos.left,
          width: 360,
          maxWidth: "calc(100vw - 28px)",
          zIndex: Z_CARD,
          border: "1px solid var(--border)",
          boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase tracking-wide text-[var(--text-faint)]">
            Step {currentIndex + 1} of {totalSteps}
          </span>
          <button
            className="text-[11px] text-[var(--text-faint)] hover:text-[var(--text-dim)]"
            onClick={tour.exitTour}
          >
            Exit tour ✕
          </button>
        </div>
        <h3 className="text-[13px] font-semibold mb-2">{currentStep.title}</h3>
        <div className="flex flex-col gap-2 mb-3">
          {currentStep.body.map((paragraph, i) => (
            <p key={i} className="text-[12px] text-[var(--text-dim)] leading-relaxed">
              {paragraph}
            </p>
          ))}
        </div>
        {!showNext ? (
          <p className="text-[11px] text-[var(--accent)] font-medium mb-3">
            {currentStep.advance.type === "run-experiment" ? "Waiting for the run to finish…" : "Click the highlighted element to continue."}
          </p>
        ) : null}
        <div className="flex items-center justify-between">
          <button
            className="text-[11px] text-[var(--text-faint)] hover:text-[var(--text-dim)]"
            onClick={tour.restartTour}
          >
            Restart tour
          </button>
          <div className="flex gap-2">
            <button
              className="px-3 py-1.5 rounded-md bg-[var(--bg-panel-raised)] text-[var(--text-dim)] text-[12px] disabled:opacity-40"
              onClick={tour.goBack}
              disabled={currentIndex === 0}
            >
              Back
            </button>
            {showNext ? (
              <button
                className="px-3 py-1.5 rounded-md bg-[var(--accent)] text-black text-[12px] font-medium"
                onClick={tour.goNext}
              >
                {currentStep.nextLabel ?? "Next"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}

function frameStyle(box: { top: number; left: number; width: number; height: number }): React.CSSProperties {
  return {
    position: "fixed",
    top: box.top,
    left: box.left,
    width: box.width,
    height: box.height,
    background: "rgba(5,7,9,0.72)",
    zIndex: Z_FRAME,
    pointerEvents: "auto",
  };
}
