/**
 * NTRP Color System - Monochrome + Configurable Accent
 * Minimalist: white text, single accent, gray muted.
 */

// Available accent colors
export const accentColors = {
  blue: { primary: "#7AA2F7", shimmer: "#B4D0FF" },
  green: { primary: "#9ECE6A", shimmer: "#C3E88D" },
  purple: { primary: "#BB9AF7", shimmer: "#D4BFFF" },
  pink: { primary: "#F7768E", shimmer: "#FFB2C1" },
  orange: { primary: "#FF9E64", shimmer: "#FFCB9E" },
  cyan: { primary: "#7DCFFF", shimmer: "#B4E4FF" },
  yellow: { primary: "#E0AF68", shimmer: "#FFD699" },
  red: { primary: "#F28B82", shimmer: "#FFBBB5" },
} as const;

export type AccentColor = keyof typeof accentColors;

// Default accent color
let currentAccent: AccentColor = "blue";

// Get/set the current accent color
export function setAccentColor(color: AccentColor) {
  currentAccent = color;
}

export function getAccentColor(): AccentColor {
  return currentAccent;
}

// Brand colors (dynamic based on accent)
export const brand = {
  get primary() { return accentColors[currentAccent].primary; },
  muted: "#71717A",        // Zinc 500
} as const;

// Semantic colors
export const colors = {
  // Text
  text: {
    primary: "#FAFAFA",    // Zinc 50
    secondary: "#A1A1AA",  // Zinc 400
    muted: "#71717A",      // Zinc 500
    disabled: "#52525B",   // Zinc 600
  },
  
  // Status
  status: {
    get success() { return accentColors[currentAccent].primary; },
    error: "#EF4444",      // Red 500
    warning: "#FBBF24",    // Amber 400
    get processing() { return accentColors[currentAccent].primary; },
    get processingShimmer() { return accentColors[currentAccent].shimmer; },
  },
  
  // Selection
  selection: {
    get active() { return accentColors[currentAccent].primary; },
    get indicator() { return accentColors[currentAccent].primary; },
  },
  
  // UI elements
  panel: {
    get title() { return accentColors[currentAccent].primary; },
    subtitle: "#A1A1AA",
  },
  
  tabs: {
    get active() { return accentColors[currentAccent].primary; },
    inactive: "#71717A",
    separator: "#3F3F46",  // Zinc 700
  },
  
  list: {
    itemText: "#FAFAFA",
    get itemTextSelected() { return accentColors[currentAccent].primary; },
    itemDetail: "#71717A",
    scrollArrow: "#71717A",
  },
  
  keyValue: {
    label: "#FAFAFA",
    get value() { return accentColors[currentAccent].primary; },
  },
  
  divider: "#3F3F46",
  footer: "#71717A",
  
  // Diff
  diff: {
    added: "#4ADE80",
    addedBg: "#14532D",
    removed: "#F87171",
    removedBg: "#7F1D1D",
  },
  
  // Tool states
  tool: {
    pending: "#A1A1AA",
    running: "#FBBF24",
    get completed() { return accentColors[currentAccent].primary; },
    error: "#EF4444",
  },
} as const;

