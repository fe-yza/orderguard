"use client";

import { useTour } from "@/lib/tour/TourContext";

export function TourNavButton() {
  const tour = useTour();
  return (
    <button
      onClick={tour.restartTour}
      className="text-[var(--text-dim)] hover:text-[var(--text)]"
    >
      Guided tour
    </button>
  );
}
