/**
 * APCA contrast validator — Phase 1 of the design-system tokens spec.
 *
 * For every palette × {light, dark}, compute APCA Lc for the five
 * foreground/background pairs the spec lists and emit:
 *   - a table to stdout
 *   - docs/internal/contrast-report.md
 *
 * Run from repo root:  bun run apps/desktop/scripts/validate-contrast.ts
 *
 * The APCA implementation below is vendored from the public W3C/Myndex
 * SAPC-APCA reference (https://github.com/Myndex/apca-w3, MIT). Only
 * `sRGBtoY` and `APCAcontrast` are needed; copied verbatim with light
 * cosmetic changes (TS types).
 */
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  PALETTE_TOKENS,
  LIGHTNESS_STEPS,
  type Oklch,
  type Ramp12,
} from "../src/lib/tokens/color";
import type { PaletteId } from "../src/lib/palettes";

// ─── OKLCH → sRGB ────────────────────────────────────────────
// Reference conversion (Björn Ottosson). Returns 0–255 channels,
// clamped (out-of-gamut colors snap to the cube; that's fine for APCA).

function oklchToSrgb({ l, c, h }: Oklch): [number, number, number] {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);

  // OKLab → linear sRGB
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.2914855480 * b;

  const lc = l_ * l_ * l_;
  const mc = m_ * m_ * m_;
  const sc = s_ * s_ * s_;

  const r =  4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc;
  const g = -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc;
  const bl =  -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc;

  // linear → gamma (sRGB)
  const enc = (v: number) => {
    if (v <= 0) return 0;
    if (v >= 1) return 1;
    return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
  };

  return [
    Math.round(enc(r) * 255),
    Math.round(enc(g) * 255),
    Math.round(enc(bl) * 255),
  ];
}

// ─── APCA (vendored, Myndex SAPC reference) ──────────────────
// Constants from apca-w3 0.1.9. Lc returned in the conventional sign:
//   positive for dark text on light bg, negative for light on dark.
// We report |Lc| since the spec targets are magnitudes.

const mainTRC = 2.4;
const Rco = 0.2126729;
const Gco = 0.7151522;
const Bco = 0.0721750;

const normBG = 0.56;
const normTXT = 0.57;
const revTXT = 0.62;
const revBG = 0.65;

const blkThrs = 0.022;
const blkClmp = 1.414;
const scaleBoW = 1.14;
const scaleWoB = 1.14;
const loBoWoffset = 0.027;
const loWoBoffset = 0.027;
const deltaYmin = 0.0005;
const loClip = 0.1;

function sRGBtoY(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((v) => Math.pow(v / 255, mainTRC));
  return Rco * r + Gco * g + Bco * b;
}

function apcaContrast(txt: [number, number, number], bg: [number, number, number]): number {
  let Ytxt = sRGBtoY(txt);
  let Ybg = sRGBtoY(bg);

  if (Ytxt < blkThrs) Ytxt += Math.pow(blkThrs - Ytxt, blkClmp);
  if (Ybg < blkThrs) Ybg += Math.pow(blkThrs - Ybg, blkClmp);

  if (Math.abs(Ybg - Ytxt) < deltaYmin) return 0;

  let outputContrast: number;
  if (Ybg > Ytxt) {
    // normal polarity, dark text on light bg
    const SAPC = (Math.pow(Ybg, normBG) - Math.pow(Ytxt, normTXT)) * scaleBoW;
    outputContrast = SAPC < loClip ? 0 : SAPC - loBoWoffset;
  } else {
    // reverse polarity, light text on dark bg
    const SAPC = (Math.pow(Ybg, revBG) - Math.pow(Ytxt, revTXT)) * scaleWoB;
    outputContrast = SAPC > -loClip ? 0 : SAPC + loWoBoffset;
  }
  return outputContrast * 100;
}

// ─── Token resolution ────────────────────────────────────────
// Map the spec's semantic pair names to concrete ramp indices. Step
// indices follow LIGHTNESS_STEPS (0-based: index 0 = step 1 = app bg).

interface Pair {
  label: string;
  fg: (n: Ramp12, a: Ramp12) => Oklch;
  bg: (n: Ramp12, a: Ramp12) => Oklch;
  target: number; // |Lc|
}

const PAIRS: Pair[] = [
  {
    label: "ink-on-bg",
    fg: (n) => n[LIGHTNESS_STEPS.TEXT_HIGH], // step 12
    bg: (n) => n[LIGHTNESS_STEPS.APP_BG],    // step 1
    target: 60,
  },
  {
    label: "ink-soft-on-bg",
    fg: (n) => n[LIGHTNESS_STEPS.TEXT_MUTED + 0], // step 11 (no dedicated soft yet)
    bg: (n) => n[LIGHTNESS_STEPS.APP_BG],
    target: 45,
  },
  {
    label: "muted-on-bg",
    fg: (n) => n[LIGHTNESS_STEPS.TEXT_MUTED], // step 11
    bg: (n) => n[LIGHTNESS_STEPS.APP_BG],
    target: 45,
  },
  {
    label: "accent-on-bg",
    fg: (_n, a) => a[LIGHTNESS_STEPS.TEXT_MUTED], // accent step 11 (label/icon text use)
    bg: (n) => n[LIGHTNESS_STEPS.APP_BG],
    target: 45,
  },
  {
    label: "accent-fg-on-accent",
    // White-ish foreground on the solid accent fill (step 9).
    fg: (n) => n[LIGHTNESS_STEPS.APP_BG],
    bg: (_n, a) => a[LIGHTNESS_STEPS.SOLID],
    target: 60,
  },
];

interface RowResult {
  palette: PaletteId;
  theme: "light" | "dark";
  pair: string;
  lc: number;
  target: number;
  pass: boolean;
}

function lcFor(fg: Oklch, bg: Oklch): number {
  return Math.abs(apcaContrast(oklchToSrgb(fg), oklchToSrgb(bg)));
}

function evaluate(): RowResult[] {
  const rows: RowResult[] = [];
  for (const [id, tokens] of Object.entries(PALETTE_TOKENS) as [PaletteId, typeof PALETTE_TOKENS[PaletteId]][]) {
    for (const theme of ["light", "dark"] as const) {
      const ramps = tokens[theme];
      for (const pair of PAIRS) {
        const fg = pair.fg(ramps.neutral, ramps.accent);
        const bg = pair.bg(ramps.neutral, ramps.accent);
        const lc = lcFor(fg, bg);
        rows.push({
          palette: id,
          theme,
          pair: pair.label,
          lc: Math.round(lc * 10) / 10,
          target: pair.target,
          pass: lc >= pair.target,
        });
      }
    }
  }
  return rows;
}

function fmtTable(rows: RowResult[]): string {
  const header = "| Palette | Theme | Pair | Lc | Target | Status |\n|---|---|---|---:|---:|:---:|\n";
  const body = rows
    .map(
      (r) =>
        `| ${r.palette} | ${r.theme} | ${r.pair} | ${r.lc.toFixed(1)} | ${r.target} | ${r.pass ? "✓" : "❌"} |`,
    )
    .join("\n");
  return header + body + "\n";
}

function fmtStdout(rows: RowResult[]): string {
  // Simple plain-text table for terminal.
  const cols = [
    ["palette", 12],
    ["theme", 6],
    ["pair", 22],
    ["lc", 7],
    ["target", 7],
    ["status", 6],
  ] as const;
  const pad = (s: string, n: number) => s.length >= n ? s.slice(0, n) : s + " ".repeat(n - s.length);
  let out = cols.map(([h, n]) => pad(h, n)).join(" ") + "\n";
  out += cols.map(([, n]) => "-".repeat(n)).join(" ") + "\n";
  for (const r of rows) {
    out += [
      pad(r.palette, 12),
      pad(r.theme, 6),
      pad(r.pair, 22),
      pad(r.lc.toFixed(1), 7),
      pad(String(r.target), 7),
      pad(r.pass ? "PASS" : "FAIL", 6),
    ].join(" ") + "\n";
  }
  return out;
}

function main() {
  const rows = evaluate();
  const fails = rows.filter((r) => !r.pass);

  console.log(fmtStdout(rows));
  console.log(`\nTotal: ${rows.length}   Pass: ${rows.length - fails.length}   Fail: ${fails.length}`);

  const reportPath = resolve(import.meta.dirname, "..", "..", "..", "docs", "internal", "contrast-report.md");
  const md =
    "# APCA contrast report\n\n" +
    `Generated by \`scripts/validate-contrast.ts\` on ${new Date().toISOString().slice(0, 10)}.\n\n` +
    "Targets: body text Lc ≥ 60, secondary/icons Lc ≥ 45 (Radix/APCA defaults).\n\n" +
    "Phase 1 emits this report against the OKLCH ramps defined in `apps/desktop/src/lib/tokens/color.ts`. " +
    "Failing rows are addressed in Phase 4 (color sweep) by adjusting individual ramp steps.\n\n" +
    `**Summary**: ${rows.length - fails.length} pass / ${fails.length} fail of ${rows.length} pairs.\n\n` +
    fmtTable(rows) +
    (fails.length
      ? "\n## Failing rows\n\n" + fmtTable(fails)
      : "\n_All pairs pass._\n");
  writeFileSync(reportPath, md);
  console.log(`\nWrote ${reportPath}`);
}

main();
