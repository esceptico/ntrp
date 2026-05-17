/**
 * Color tokens — Phase 1 of the design-system tokens spec
 * (docs/superpowers/specs/2026-05-17-design-system-tokens-design.md §2.1).
 *
 * Per-palette 12-step OKLCH ramps for neutrals + accent, in both light
 * and dark variants. This file is **data only** in Phase 1 — no
 * runtime application logic (palette → CSS variables is Phase 4).
 *
 * Scale semantics (Radix-derived, see docs/research/color-rules.md):
 *
 *   1  — app background (chat scroll, page bg)
 *   2  — subtle background (sunken)
 *   3  — UI element background (rest state for cards, rails)
 *   4  — UI element background (hover)
 *   5  — UI element background (active / pressed)
 *   6  — subtle borders & separators (line-soft)
 *   7  — UI element borders (line)
 *   8  — stronger borders, focus rings (line-strong)
 *   9  — solid backgrounds (saturated accent fill, button bg)
 *   10 — solid backgrounds (hover)
 *   11 — low-contrast text (muted, secondary labels)
 *   12 — high-contrast text (ink, primary copy)
 *
 * Body copy targets step 12 over step 1 (APCA Lc ≥ 60).
 * Secondary/muted targets step 11 over step 1 (APCA Lc ≥ 45).
 */
import type { PaletteId } from "../palettes";

/** OKLCH triple: lightness 0–1, chroma 0+, hue degrees. */
export interface Oklch {
  l: number;
  c: number;
  h: number;
}

/** 12-step ramp indexed by the Radix scale documented above. */
export type Ramp12 = readonly [
  Oklch, Oklch, Oklch, Oklch, Oklch, Oklch,
  Oklch, Oklch, Oklch, Oklch, Oklch, Oklch,
];

export interface PaletteRamps {
  /** Step 1 is brightest in light, darkest in dark. */
  neutral: Ramp12;
  /** Accent ramp — step 9 is the canonical solid accent. */
  accent: Ramp12;
}

export interface PaletteTokens {
  light: PaletteRamps;
  dark: PaletteRamps;
}

/** Convenience index names for human-readable lookups. */
export const LIGHTNESS_STEPS = {
  APP_BG: 0,
  SUBTLE_BG: 1,
  UI_REST: 2,
  UI_HOVER: 3,
  UI_ACTIVE: 4,
  LINE_SOFT: 5,
  LINE: 6,
  LINE_STRONG: 7,
  SOLID: 8,
  SOLID_HOVER: 9,
  TEXT_MUTED: 10,
  TEXT_HIGH: 11,
} as const;

const o = (l: number, c: number, h: number): Oklch => ({ l, c, h });

// ─── Generic neutral ramps ──────────────────────────────────
// Most palettes share the same neutral lightness/chroma curve; only the
// hue differs to give the surface a faint tint. Per-palette overrides
// are listed in PALETTE_TOKENS below; this is the baseline.

function neutralRampLight(hue: number, tint = 0.004): Ramp12 {
  return [
    o(0.991, tint * 0.5, hue), // 1 app bg
    o(0.974, tint * 0.6, hue), // 2 subtle
    o(0.955, tint, hue),       // 3 ui rest
    o(0.935, tint * 1.1, hue), // 4 ui hover
    o(0.910, tint * 1.2, hue), // 5 ui active
    o(0.890, tint * 1.2, hue), // 6 line soft
    o(0.855, tint * 1.4, hue), // 7 line
    o(0.790, tint * 1.6, hue), // 8 line strong
    o(0.620, tint * 2.0, hue), // 9 solid
    o(0.560, tint * 2.0, hue), // 10 solid hover
    o(0.450, tint * 1.6, hue), // 11 muted text
    o(0.205, tint * 1.0, hue), // 12 ink
  ] as const;
}

function neutralRampDark(hue: number, tint = 0.006): Ramp12 {
  return [
    o(0.165, tint * 0.8, hue), // 1 app bg
    o(0.195, tint, hue),       // 2 subtle
    o(0.225, tint * 1.1, hue), // 3 ui rest
    o(0.260, tint * 1.2, hue), // 4 ui hover
    o(0.295, tint * 1.3, hue), // 5 ui active
    o(0.330, tint * 1.3, hue), // 6 line soft
    o(0.380, tint * 1.3, hue), // 7 line
    o(0.450, tint * 1.4, hue), // 8 line strong
    o(0.620, tint * 1.6, hue), // 9 solid
    o(0.680, tint * 1.6, hue), // 10 solid hover
    o(0.745, tint * 1.2, hue), // 11 muted text
    o(0.945, tint * 0.6, hue), // 12 ink
  ] as const;
}

/**
 * Accent ramp built from a target solid color (step 9). Lower steps
 * desaturate and lighten for backgrounds; upper steps darken/lighten
 * for hover and text. Dark mode reduces chroma ~30% per research
 * (docs/research/color-rules.md "Dark mode accent desaturation").
 */
function accentRampLight(target: Oklch): Ramp12 {
  const h = target.h;
  return [
    o(0.985, target.c * 0.10, h), // 1
    o(0.965, target.c * 0.18, h), // 2
    o(0.935, target.c * 0.30, h), // 3
    o(0.895, target.c * 0.45, h), // 4
    o(0.840, target.c * 0.60, h), // 5
    o(0.770, target.c * 0.75, h), // 6
    o(0.700, target.c * 0.90, h), // 7
    o(0.640, target.c * 1.00, h), // 8
    o(target.l, target.c, h),     // 9 — solid
    o(Math.max(0.30, target.l - 0.06), target.c, h), // 10
    o(Math.max(0.40, target.l - 0.10), target.c * 0.95, h), // 11
    o(Math.max(0.25, target.l - 0.20), target.c * 0.85, h), // 12
  ] as const;
}

function accentRampDark(target: Oklch): Ramp12 {
  const h = target.h;
  // Dark mode: desaturate ~30%, lift step 9 lightness so it reads as
  // luminous rather than muddy on dark surfaces.
  const c = target.c * 0.7;
  const l9 = Math.min(0.80, target.l + 0.04);
  return [
    o(0.180, c * 0.20, h), // 1
    o(0.215, c * 0.30, h), // 2
    o(0.260, c * 0.45, h), // 3
    o(0.310, c * 0.60, h), // 4
    o(0.365, c * 0.75, h), // 5
    o(0.420, c * 0.85, h), // 6
    o(0.490, c * 0.95, h), // 7
    o(0.575, c * 1.00, h), // 8
    o(l9, c, h),           // 9 — solid
    o(Math.min(0.85, l9 + 0.05), c, h), // 10
    o(Math.min(0.82, l9 + 0.08), c * 0.85, h), // 11
    o(0.945, c * 0.45, h), // 12
  ] as const;
}

// ─── Per-palette accent anchors (step 9) ─────────────────────
// Hues chosen to match each brand's documented accent color, expressed
// in OKLCH. Final chroma may be tuned in Phase 4 after APCA validation.

interface PaletteAnchor {
  neutralHueLight: number;
  neutralHueDark: number;
  neutralTintLight?: number;
  neutralTintDark?: number;
  accentLight: Oklch;
  accentDark: Oklch;
}

const ANCHORS: Record<PaletteId, PaletteAnchor> = {
  // Warm — orange accent, cream neutrals (current default).
  warm: {
    neutralHueLight: 70,
    neutralHueDark: 60,
    neutralTintLight: 0.008,
    neutralTintDark: 0.010,
    accentLight: o(0.610, 0.155, 50),
    // Dark step 9 lifted from 0.700 → 0.760 to clear APCA Lc 60 for
    // neutral-1 (the white-ish fg) on the solid accent fill.
    accentDark: o(0.760, 0.155, 55),
  },
  // Graphite — teal accent, near-pure neutrals.
  graphite: {
    neutralHueLight: 210,
    neutralHueDark: 220,
    accentLight: o(0.610, 0.110, 175),
    accentDark: o(0.790, 0.105, 175),
  },
  // Raycast — red accent.
  raycast: {
    neutralHueLight: 0,
    neutralHueDark: 0,
    neutralTintLight: 0.002,
    neutralTintDark: 0.002,
    accentLight: o(0.660, 0.200, 22),
    // Lifted dark step 9 lightness for APCA Lc ≥ 60 on accent-fg.
    accentDark: o(0.760, 0.180, 22),
  },
  // Notion — monochrome (accent is near-black on light, near-white on dark).
  notion: {
    neutralHueLight: 60,
    neutralHueDark: 60,
    neutralTintLight: 0.003,
    neutralTintDark: 0.004,
    accentLight: o(0.215, 0.005, 60),
    accentDark: o(0.965, 0.004, 60),
  },
};

function buildPalette(id: PaletteId): PaletteTokens {
  const a = ANCHORS[id];
  return {
    light: {
      neutral: neutralRampLight(a.neutralHueLight, a.neutralTintLight),
      accent: accentRampLight(a.accentLight),
    },
    dark: {
      neutral: neutralRampDark(a.neutralHueDark, a.neutralTintDark),
      accent: accentRampDark(a.accentDark),
    },
  };
}

export const PALETTE_TOKENS: Record<PaletteId, PaletteTokens> = {
  warm: buildPalette("warm"),
  graphite: buildPalette("graphite"),
  raycast: buildPalette("raycast"),
  notion: buildPalette("notion"),
};

/** Format an OKLCH triple as a CSS `oklch(...)` string. */
export function formatOklch(c: Oklch): string {
  const l = (c.l * 100).toFixed(2);
  return `oklch(${l}% ${c.c.toFixed(4)} ${c.h.toFixed(2)})`;
}

/**
 * Write `--color-neutral-{1..12}` and `--color-accent-{1..12}` to the
 * root element for the given palette × theme. Additive — the legacy
 * `--color-bg`, `--color-surface`, … vars are still set by the
 * `:root.palette-*` blocks in `styles.css`. Aliases on `:root` map the
 * legacy names to ramp steps as a fallback; the per-palette blocks
 * override them so visuals don't change in Phase 4.
 */
export function applyTokens(palette: PaletteId, theme: "light" | "dark"): void {
  const root = document.documentElement;
  const ramps = PALETTE_TOKENS[palette][theme];
  for (let i = 0; i < 12; i++) {
    root.style.setProperty(`--color-neutral-${i + 1}`, formatOklch(ramps.neutral[i]));
    root.style.setProperty(`--color-accent-${i + 1}`, formatOklch(ramps.accent[i]));
  }
}
