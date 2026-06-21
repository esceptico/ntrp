export type TooltipSide = "top" | "bottom" | "left" | "right";

export interface TooltipRect {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
}

export interface TooltipSize {
  width: number;
  height: number;
}

export interface TooltipViewport {
  width: number;
  height: number;
}

export interface TooltipPlacement {
  side: TooltipSide;
  top: number;
  left: number;
}

const clamp = (value: number, min: number, max: number) => {
  if (max < min) return min;
  return Math.min(max, Math.max(min, value));
};

export function calculateTooltipPlacement({
  preferredSide,
  trigger,
  tooltip,
  viewport,
  gap,
  safeMargin,
}: {
  preferredSide: TooltipSide;
  trigger: TooltipRect;
  tooltip: TooltipSize;
  viewport: TooltipViewport;
  gap: number;
  safeMargin: number;
}): TooltipPlacement {
  let side = preferredSide;
  const room = {
    top: trigger.top - gap - safeMargin,
    bottom: viewport.height - trigger.bottom - gap - safeMargin,
    left: trigger.left - gap - safeMargin,
    right: viewport.width - trigger.right - gap - safeMargin,
  };

  if (preferredSide === "top" || preferredSide === "bottom") {
    const opposite = preferredSide === "top" ? "bottom" : "top";
    if (tooltip.height > room[preferredSide] && room[opposite] > room[preferredSide]) {
      side = opposite;
    }
  } else {
    const opposite = preferredSide === "left" ? "right" : "left";
    if (tooltip.width > room[preferredSide] && room[opposite] > room[preferredSide]) {
      side = opposite;
    }
  }

  const cx = trigger.left + trigger.width / 2;
  const cy = trigger.top + trigger.height / 2;
  let top: number;
  let left: number;

  if (side === "top") {
    top = trigger.top - gap - tooltip.height;
    left = cx - tooltip.width / 2;
  } else if (side === "bottom") {
    top = trigger.bottom + gap;
    left = cx - tooltip.width / 2;
  } else if (side === "left") {
    top = cy - tooltip.height / 2;
    left = trigger.left - gap - tooltip.width;
  } else {
    top = cy - tooltip.height / 2;
    left = trigger.right + gap;
  }

  return {
    side,
    top: clamp(top, safeMargin, viewport.height - tooltip.height - safeMargin),
    left: clamp(left, safeMargin, viewport.width - tooltip.width - safeMargin),
  };
}
