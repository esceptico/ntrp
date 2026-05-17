import { useEffect } from "react";
import { useStore } from "../store";
import type { GlassParams, GlassPrefs, GlassVariantId } from "../store";

const VARIANT_IDS: GlassVariantId[] = [
  "frosted",
  "heavy",
  "static",
  "clear",
  "smoke",
  "milk",
];

/** Write the user's glass prefs onto :root as CSS custom properties.
 *  Every .glass-{variant} rule reads these via `var(--gp-{variant}-X, fallback)`,
 *  so absent props fall back to the variant's hardcoded defaults. */
function applyGlassPrefs(glass: GlassPrefs): void {
  const root = document.documentElement;
  for (const id of VARIANT_IDS) {
    const p = glass[id];
    if (!p) continue;
    setVariant(root, id, p);
  }
}

function setVariant(
  root: HTMLElement,
  id: GlassVariantId,
  p: GlassParams,
): void {
  // Tint is a 0–100% value the user adjusts. We resolve it to an alpha
  // and inject as a full rgba() so variants don't have to compose it.
  const alpha = clamp(p.tint, 0, 100) / 100;
  root.style.setProperty(`--gp-${id}-tint`, tintFor(id, alpha));
  root.style.setProperty(`--gp-${id}-blur`, `${clamp(p.blur, 0, 60)}px`);
  root.style.setProperty(`--gp-${id}-saturate`, `${clamp(p.saturate, 0, 400)}%`);
  root.style.setProperty(`--gp-${id}-rim`, String(clamp(p.rim, 0, 100) / 100));
}

/** Each variant's base color differs (white vs ink-blue for smoke). The
 *  user-controlled alpha is mixed onto that base. */
function tintFor(id: GlassVariantId, alpha: number): string {
  if (id === "smoke") return `rgba(10, 10, 30, ${alpha})`;
  return `rgba(255, 255, 255, ${alpha})`;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/** Subscribes to prefs.glass and applies the params to :root every change. */
export function useGlassEffect(): void {
  const glass = useStore((s) => s.prefs.glass);
  useEffect(() => {
    applyGlassPrefs(glass);
  }, [glass]);
}
