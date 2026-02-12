/**
 * NTRP Color System — Monochrome
 * No colors. Just gray.
 *
 * Base scale (perceptually even, dark→light):
 *   0: #101010   1: #181818   2: #212121   3: #2c2c2c
 *   4: #3a3a3a   5: #505050   6: #6a6a6a   7: #888888
 *   8: #a8a8a8   9: #c8c8c8  10: #e0e0e0  11: #f0f0f0
 */

const g = {
  0: "#101010",
  1: "#181818",
  2: "#212121",
  3: "#2c2c2c",
  4: "#3a3a3a",
  5: "#505050",
  6: "#6a6a6a",
  7: "#888888",
  8: "#a8a8a8",
  9: "#c8c8c8",
  10: "#e0e0e0",
  11: "#f0f0f0",
} as const;

export const accentColors = {
  gray: { primary: g[9], shimmer: g[10] },
} as const;

export type AccentColor = keyof typeof accentColors;

let currentAccent: AccentColor = "gray";

export function syncAccentColor(color: AccentColor) {
  currentAccent = color;
}

export const colors = {
  text: {
    primary: g[9],
    secondary: g[7],
    muted: g[6],
    disabled: g[5],
  },

  status: {
    success: g[7],
    error: g[7],
    warning: g[7],
    processing: g[9],
    processingShimmer: g[10],
  },

  selection: {
    active: g[9],
    indicator: g[9],
  },

  panel: {
    title: g[9],
    subtitle: g[7],
  },

  tabs: {
    active: g[9],
    inactive: g[6],
    separator: g[4],
  },

  list: {
    itemText: g[9],
    itemTextSelected: g[9],
    itemDetail: g[6],
    scrollArrow: g[6],
  },

  keyValue: {
    label: g[9],
    value: g[7],
  },

  background: {
    base: g[1],
    panel: g[0],
    element: g[3],
    menu: g[3],
  },

  border: g[4],

  divider: g[4],
  footer: g[6],

  diff: {
    added: g[7],
    addedBg: g[3],
    removed: g[6],
    removedBg: g[2],
  },

  tool: {
    pending: g[6],
    running: g[7],
    completed: g[9],
    error: g[7],
  },
} as const;
