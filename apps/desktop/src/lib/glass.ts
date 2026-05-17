import { useEffect } from "react";
import { useStore } from "../store";
import type { GlassParams } from "../store";

/** Write the user's glass params onto :root as CSS custom properties.
 *  `.glass-surface` reads these via `var(--gp-X, fallback)`. Tint is
 *  written as a raw 0–1 alpha so each theme's CSS can compose the rgba
 *  with its own base color (white in light, white-over-dark in dark
 *  at a calibrated multiplier so the slider isn't overpowering). */
function applyGlassParams(p: GlassParams): void {
  const root = document.documentElement;
  root.style.setProperty("--gp-tint-alpha", String(clamp(p.tint, 0, 100) / 100));
  root.style.setProperty("--gp-blur", `${clamp(p.blur, 0, 60)}px`);
  root.style.setProperty("--gp-saturate", `${clamp(p.saturate, 0, 400)}%`);
  root.style.setProperty("--gp-rim", String(clamp(p.rim, 0, 100) / 100));
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/** Subscribes to prefs.glass and applies the params to :root every change. */
export function useGlassEffect(): void {
  const glass = useStore((s) => s.prefs.glass);
  useEffect(() => {
    applyGlassParams(glass);
  }, [glass]);
}
