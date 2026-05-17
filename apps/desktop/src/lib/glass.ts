import { useEffect } from "react";
import { useStore } from "../store";
import type { GlassParams } from "../store";

/** Write the user's glass params onto :root as CSS custom properties.
 *  `.glass-surface` reads these via `var(--gp-X, fallback)`, so absent
 *  props fall back to the hardcoded defaults. */
function applyGlassParams(p: GlassParams): void {
  const root = document.documentElement;
  const alpha = clamp(p.tint, 0, 100) / 100;
  root.style.setProperty("--gp-tint", `rgba(255, 255, 255, ${alpha})`);
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
