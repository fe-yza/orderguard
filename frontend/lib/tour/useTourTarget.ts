"use client";

import { useEffect, useState } from "react";

export interface TargetRect {
  top: number;
  left: number;
  width: number;
  height: number;
  bottom: number;
  right: number;
}

function measure(el: Element): TargetRect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height, bottom: r.bottom, right: r.right };
}

/**
 * Tracks the live position of the element matching `selector`, re-measuring
 * on scroll/resize and whenever the DOM changes (a MutationObserver, not a
 * polling timer — this is purely "find and track the target," not a
 * substitute for the tour's own step-advance logic, which never runs off a
 * timer). Returns null until/unless the element exists — callers treat a
 * persistent null as "this step's target isn't on the page right now."
 */
export function useTourTarget(selector: string | null): { element: Element | null; rect: TargetRect | null } {
  const [element, setElement] = useState<Element | null>(null);
  const [rect, setRect] = useState<TargetRect | null>(null);

  /* eslint-disable react-hooks/set-state-in-effect -- this hook's entire
     job is syncing React state to an external system (the live DOM via
     MutationObserver/ResizeObserver), which is exactly the case React's
     own docs list as a valid reason to setState from inside an effect. */
  useEffect(() => {
    if (!selector) {
      setElement(null);
      setRect(null);
      return;
    }

    let current: Element | null = null;
    let resizeObserver: ResizeObserver | null = null;

    const sync = () => {
      const found = document.querySelector(selector);
      if (found !== current) {
        current = found;
        setElement(found);
        resizeObserver?.disconnect();
        if (found) {
          resizeObserver = new ResizeObserver(() => setRect(measure(found)));
          resizeObserver.observe(found);
        }
      }
      if (found) setRect(measure(found));
    };

    sync();
    const mutationObserver = new MutationObserver(sync);
    mutationObserver.observe(document.body, { childList: true, subtree: true, attributes: true });
    window.addEventListener("scroll", sync, true);
    window.addEventListener("resize", sync);

    return () => {
      mutationObserver.disconnect();
      resizeObserver?.disconnect();
      window.removeEventListener("scroll", sync, true);
      window.removeEventListener("resize", sync);
    };
  }, [selector]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return { element, rect };
}
