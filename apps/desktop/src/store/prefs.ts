import type { GlassPrefs, Prefs } from "./types";

export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 380;
export const SIDEBAR_SNAP_POINTS = [220, 244, 280, 320] as const;
export const SIDEBAR_SNAP_THRESHOLD_PX = 12;

export const DEFAULT_QUICK_CAPTURE_SHORTCUT = "CommandOrControl+Shift+Space";

const PREFS_KEY = "ntrp.desktop.prefs";
const PREFS_VERSION = 4;

/* The canonical glass material. Defaults match the historic "frosted"
 * recipe — readable foreground over a lively background. */
export const DEFAULT_GLASS_PREFS: GlassPrefs = {
  tint: 35,
  blur: 20,
  saturate: 180,
  rim: 60,
};

export const DEFAULT_PREFS: Prefs = {
  thinkingAnimation: "comet",
  thinkingIntensity: "normal",
  theme: "system",
  palette: "graphite",
  material: "linen",
  sidebarHidden: false,
  sidebarWidth: 272,
  showReasoningInChat: true,
  quickCaptureShortcut: DEFAULT_QUICK_CAPTURE_SHORTCUT,
  glass: DEFAULT_GLASS_PREFS,
};

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs> & { prefsVersion?: number };
    const ver = parsed.prefsVersion ?? 1;
    // One-time migration: bump anyone still on the legacy "warm" default
    // to graphite when introducing the new default. Users who explicitly
    // want warm can flip back from Settings → Appearance.
    if (ver < 2 && parsed.palette === "warm") {
      parsed.palette = "graphite";
    }
    // v2 → v3: glass prefs shipped with wrong rim defaults (60/75/60/35
    // instead of 10/0/0/0). Force a reset to the corrected defaults so
    // existing users don't carry the over-bright rim forward.
    // v3 → v4: glass framework collapsed from a per-variant Record to a
    // single GlassParams. Reset rather than trying to pick a variant.
    if (ver < 4) {
      parsed.glass = DEFAULT_GLASS_PREFS;
    }
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function persistPrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ ...prefs, prefsVersion: PREFS_VERSION }),
    );
  } catch {
    /* localStorage unavailable — non-fatal */
  }
}

// Auto mode (skip approvals) is conceptually session state, not a Prefs
// field — but we persist it to localStorage so closing the app and
// reopening doesn't silently flip the user back into approval-required
// mode without warning. Stored separately from `prefs` so the migration
// surface stays narrow.
const SKIP_APPROVALS_KEY = "ntrp.desktop.skipApprovals";

export function loadSkipApprovals(): boolean {
  try {
    return localStorage.getItem(SKIP_APPROVALS_KEY) === "true";
  } catch {
    return false;
  }
}

export function persistSkipApprovals(value: boolean): void {
  try {
    localStorage.setItem(SKIP_APPROVALS_KEY, value ? "true" : "false");
  } catch {
    /* localStorage unavailable — non-fatal */
  }
}
