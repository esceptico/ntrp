import { useEffect } from "react";
import { useStore } from "../store";
import type { GlassParams, Material } from "../store";

/** Write the user's glass params onto :root as CSS custom properties.
 *  `.glass-surface` reads these via `var(--gp-X, fallback)`. Tint is
 *  written as a raw 0–1 alpha so each theme's CSS can compose the rgba
 *  with its own base color (white in light, white-over-dark in dark
 *  at a calibrated multiplier so the slider isn't overpowering).
 *
 *  Rim: we write the slider value to `--gp-rim-base` (the underlying
 *  user pref) and seed `--gp-rim` to the same value. Per-material
 *  interaction polish (Phase 5) overrides `--gp-rim` locally on
 *  :hover / :active by bumping it relative to `--gp-rim-base` —
 *  the base never moves, so the slider stays the source of truth. */
function applyGlassParams(p: GlassParams): void {
  const root = document.documentElement;
  root.style.setProperty("--gp-tint-alpha", String(clamp(p.tint, 0, 100) / 100));
  root.style.setProperty("--gp-blur", `${clamp(p.blur, 0, 60)}px`);
  root.style.setProperty("--gp-saturate", `${clamp(p.saturate, 0, 400)}%`);
  const rim = String(clamp(p.rim, 0, 100) / 100);
  root.style.setProperty("--gp-rim-base", rim);
  root.style.setProperty("--gp-rim", rim);
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

/** Subscribes to glass + material prefs and applies them to :root every
 *  change. Material is written as `data-material` so CSS can swap the
 *  whole .glass-surface recipe between translucent glass and solid linen
 *  via attribute selector. */
export function useGlassEffect(): void {
  const glass = useStore((s) => s.prefs.glass);
  const material = useStore((s) => s.prefs.material);
  useEffect(() => {
    applyGlassParams(glass);
  }, [glass]);
  useEffect(() => {
    applyMaterial(material);
  }, [material]);
}

function applyMaterial(m: Material): void {
  document.documentElement.dataset.material = m;
}
