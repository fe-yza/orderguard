import type { TargetRect } from "./useTourTarget";

export interface CardPosition {
  top: number;
  left: number;
}

const MARGIN = 14;

/**
 * Picks bottom/top/right/left (in that preference order) for the
 * explanation card, whichever actually fits the viewport without covering
 * the spotlighted element, falling back to a clamped bottom-of-viewport
 * position if nothing fits cleanly (small screens).
 */
export function computeCardPosition(
  target: TargetRect,
  cardWidth: number,
  cardHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): CardPosition {
  const clampLeft = (left: number) =>
    Math.max(MARGIN, Math.min(left, viewportWidth - cardWidth - MARGIN));
  const clampTop = (top: number) =>
    Math.max(MARGIN, Math.min(top, viewportHeight - cardHeight - MARGIN));

  const spaceBelow = viewportHeight - target.bottom;
  const spaceAbove = target.top;
  const spaceRight = viewportWidth - target.right;
  const spaceLeft = target.left;

  if (spaceBelow >= cardHeight + MARGIN) {
    return { top: target.bottom + MARGIN, left: clampLeft(target.left) };
  }
  if (spaceAbove >= cardHeight + MARGIN) {
    return { top: target.top - cardHeight - MARGIN, left: clampLeft(target.left) };
  }
  if (spaceRight >= cardWidth + MARGIN) {
    return { top: clampTop(target.top), left: target.right + MARGIN };
  }
  if (spaceLeft >= cardWidth + MARGIN) {
    return { top: clampTop(target.top), left: target.left - cardWidth - MARGIN };
  }
  return { top: viewportHeight - cardHeight - MARGIN, left: clampLeft((viewportWidth - cardWidth) / 2) };
}
