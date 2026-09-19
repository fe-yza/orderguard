"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { TOUR_STEPS } from "./steps";
import type { TourRuntimeFacts, TourStep } from "./types";

const INTRO_SEEN_KEY = "orderguard.tour.introSeen";
const SESSION_KEY = "orderguard.tour.session";

interface AwaitedOrder {
  runId: string;
  orderId: string;
}

interface TourSessionSnapshot {
  active: boolean;
  stepIndex: number;
  awaitedOrder: AwaitedOrder | null;
}

interface TourContextValue {
  active: boolean;
  currentStep: TourStep | null;
  currentIndex: number;
  totalSteps: number;
  showIntroModal: boolean;
  showSummaryModal: boolean;
  awaitedOrder: AwaitedOrder | null;

  startTour: () => void;
  restartTour: () => void;
  exitTour: () => void;
  dismissIntro: () => void;
  goNext: () => void;
  goBack: () => void;
  closeSummary: () => void;

  setAwaitedOrder: (order: AwaitedOrder | null) => void;
  notifyOrderOpened: (runId: string, orderId: string, hasMultipleAssessments: boolean) => void;
  notifyExperimentStatus: (status: "running" | "success" | "error", runId?: string) => void;

  /** Where the tour expects the visitor to be for the current step, or
   * null if there's nothing to navigate to (e.g. no order targeted yet). */
  expectedPath: string | null;
  onExpectedPage: boolean;
}

const TourContext = createContext<TourContextValue | null>(null);

function stepPathFor(step: TourStep, awaitedOrder: AwaitedOrder | null): string | null {
  if (step.page === "/") return "/";
  if (step.page === "/simulation-lab") return "/simulation-lab";
  if (step.page === "order-detail") {
    if (!awaitedOrder) return null;
    return `/simulations/${awaitedOrder.runId}/orders/${awaitedOrder.orderId}`;
  }
  return null;
}

function resolveSkips(startIndex: number, direction: 1 | -1, facts: TourRuntimeFacts): number {
  let i = startIndex;
  while (i >= 0 && i < TOUR_STEPS.length && TOUR_STEPS[i].skipIf?.(facts)) {
    i += direction;
  }
  return Math.max(0, Math.min(TOUR_STEPS.length - 1, i));
}

export function TourProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [showIntroModal, setShowIntroModal] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [awaitedOrder, setAwaitedOrderState] = useState<AwaitedOrder | null>(null);
  const [facts, setFacts] = useState<TourRuntimeFacts>({ orderHasRiskHistory: true });
  const [hydrated, setHydrated] = useState(false);

  // First-run intro modal + session resume — both read from storage exactly
  // once on mount, never forcing a returning visitor back into the tour.
  // This has to be an effect, not a lazy useState initializer: reading
  // sessionStorage/localStorage during the server-rendered pass would
  // throw (no `window`), and reading it in a lazy initializer would still
  // run during the client's hydration pass with a different result than
  // the server pass, producing a genuine hydration mismatch. Deferring to
  // an effect is the framework-sanctioned way to sync from a browser-only
  // store on mount — hence the narrow rule exception below.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const snapshot: TourSessionSnapshot = JSON.parse(raw);
        if (snapshot.active) {
          setActive(true);
          setStepIndex(snapshot.stepIndex);
          setAwaitedOrderState(snapshot.awaitedOrder);
          setHydrated(true);
          return;
        }
      }
    } catch {
      // ignore malformed/blocked storage — fall through to intro check
    }
    try {
      if (!localStorage.getItem(INTRO_SEEN_KEY)) {
        setShowIntroModal(true);
      }
    } catch {
      // private browsing or storage blocked — just don't auto-show
    }
    setHydrated(true);
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (!hydrated) return;
    try {
      const snapshot: TourSessionSnapshot = { active, stepIndex, awaitedOrder };
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(snapshot));
    } catch {
      // best-effort persistence only
    }
  }, [active, stepIndex, awaitedOrder, hydrated]);

  const markIntroSeen = useCallback(() => {
    try {
      localStorage.setItem(INTRO_SEEN_KEY, "1");
    } catch {
      // ignore
    }
  }, []);

  const navigateToStep = useCallback(
    (step: TourStep, order: AwaitedOrder | null) => {
      const target = stepPathFor(step, order);
      if (target && target !== pathname) {
        router.push(target);
      }
    },
    [pathname, router],
  );

  const startTour = useCallback(() => {
    markIntroSeen();
    setShowIntroModal(false);
    setShowSummaryModal(false);
    const firstIndex = resolveSkips(0, 1, facts);
    setStepIndex(firstIndex);
    setActive(true);
    navigateToStep(TOUR_STEPS[firstIndex], awaitedOrder);
  }, [awaitedOrder, facts, markIntroSeen, navigateToStep]);

  const restartTour = useCallback(() => {
    setAwaitedOrderState(null);
    setShowSummaryModal(false);
    const firstIndex = resolveSkips(0, 1, facts);
    setStepIndex(firstIndex);
    setActive(true);
    if (pathname !== "/") router.push("/");
  }, [facts, pathname, router]);

  const exitTour = useCallback(() => {
    setActive(false);
    setShowSummaryModal(false);
  }, []);

  const dismissIntro = useCallback(() => {
    markIntroSeen();
    setShowIntroModal(false);
  }, [markIntroSeen]);

  const closeSummary = useCallback(() => {
    setShowSummaryModal(false);
    setActive(false);
  }, []);

  const goNext = useCallback(() => {
    setStepIndex((i) => {
      const next = resolveSkips(i + 1, 1, facts);
      if (i + 1 > TOUR_STEPS.length - 1) {
        setActive(false);
        setShowSummaryModal(true);
        return i;
      }
      navigateToStep(TOUR_STEPS[next], awaitedOrder);
      return next;
    });
  }, [awaitedOrder, facts, navigateToStep]);

  const goBack = useCallback(() => {
    setStepIndex((i) => {
      const prev = resolveSkips(Math.max(0, i - 1), -1, facts);
      navigateToStep(TOUR_STEPS[prev], awaitedOrder);
      return prev;
    });
  }, [awaitedOrder, facts, navigateToStep]);

  const setAwaitedOrder = useCallback((order: AwaitedOrder | null) => {
    setAwaitedOrderState(order);
  }, []);

  const notifyOrderOpened = useCallback(
    (runId: string, orderId: string, hasMultipleAssessments: boolean) => {
      setFacts((f) => ({ ...f, orderHasRiskHistory: hasMultipleAssessments }));
      if (!active) return;
      const step = TOUR_STEPS[stepIndex];
      if (step.advance.type !== "click-order") return;
      if (awaitedOrder && awaitedOrder.runId === runId && awaitedOrder.orderId === orderId) {
        goNext();
      }
    },
    [active, awaitedOrder, goNext, stepIndex],
  );

  const notifyExperimentStatus = useCallback(
    (status: "running" | "success" | "error") => {
      if (!active) return;
      const step = TOUR_STEPS[stepIndex];
      if (step.advance.type !== "run-experiment") return;
      if (status === "success") goNext();
    },
    [active, goNext, stepIndex],
  );

  const currentStep = active ? TOUR_STEPS[stepIndex] ?? null : null;
  const expectedPath = currentStep ? stepPathFor(currentStep, awaitedOrder) : null;
  const onExpectedPage = expectedPath === null ? true : expectedPath === pathname;

  const value = useMemo<TourContextValue>(
    () => ({
      active,
      currentStep,
      currentIndex: stepIndex,
      totalSteps: TOUR_STEPS.length,
      showIntroModal,
      showSummaryModal,
      awaitedOrder,
      startTour,
      restartTour,
      exitTour,
      dismissIntro,
      goNext,
      goBack,
      closeSummary,
      setAwaitedOrder,
      notifyOrderOpened,
      notifyExperimentStatus,
      expectedPath,
      onExpectedPage,
    }),
    [
      active,
      currentStep,
      stepIndex,
      showIntroModal,
      showSummaryModal,
      awaitedOrder,
      startTour,
      restartTour,
      exitTour,
      dismissIntro,
      goNext,
      goBack,
      closeSummary,
      setAwaitedOrder,
      notifyOrderOpened,
      notifyExperimentStatus,
      expectedPath,
      onExpectedPage,
    ],
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used within a TourProvider");
  return ctx;
}
