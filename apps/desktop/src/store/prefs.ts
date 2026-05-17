import type { GlassPrefs, Prefs } from "./types";

export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 380;
export const SIDEBAR_SNAP_POINTS = [220, 244, 280, 320] as const;
export const SIDEBAR_SNAP_THRESHOLD_PX = 12;

export const DEFAULT_QUICK_CAPTURE_SHORTCUT = "CommandOrControl+Shift+Space";

const PREFS_KEY = "ntrp.desktop.prefs";
const PREFS_VERSION = 3;

/* Rim values match the actual CSS fallbacks. Only frosted (dark), smoke,
 * and milk have a `--gp-{variant}-rim` CSS property wired up — for
 * heavy/static/clear the slider currently has no visual effect (their
 * styles.css blocks don't include a parameterized rim inset). Defaulted
 * to 0 to signal that nothing is happening. */
export const DEFAULT_GLASS_PREFS: GlassPrefs = {
  frosted: { tint: 35, blur: 20, saturate: 180, rim: 10 },
  heavy:   { tint: 18, blur: 40, saturate: 180, rim: 0 },
  static:  { tint: 86, blur: 0,  saturate: 100, rim: 0 },
  clear:   { tint: 4,  blur: 2,  saturate: 160, rim: 0 },
  smoke:   { tint: 55, blur: 20, saturate: 120, rim: 6 },
  milk:    { tint: 50, blur: 24, saturate: 140, rim: 90 },
};

export const DEFAULT_PREFS: Prefs = {
  thinkingAnimation: "comet",
  thinkingIntensity: "normal",
  theme: "system",
  palette: "graphite",
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
    if (ver < 3) {
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
