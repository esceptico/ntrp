import type { Prefs } from "./types";

export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 380;
export const SIDEBAR_SNAP_POINTS = [220, 244, 280, 320] as const;
export const SIDEBAR_SNAP_THRESHOLD_PX = 12;

export const DEFAULT_QUICK_CAPTURE_SHORTCUT = "CommandOrControl+Shift+Space";

const PREFS_KEY = "ntrp.desktop.prefs";
const PREFS_VERSION = 8;

const RETIRED_PALETTES = new Set(["vercel", "github", "linear", "catppuccin"]);

export const DEFAULT_PREFS: Prefs = {
  thinkingAnimation: "comet",
  thinkingIntensity: "normal",
  theme: "system",
  palette: "notion",
  sidebarHidden: false,
  sidebarWidth: 272,
  quickCaptureShortcut: DEFAULT_QUICK_CAPTURE_SHORTCUT,
};

type LegacyPrefs = Partial<Prefs> & {
  prefsVersion?: number;
  material?: unknown;
  showReasoningInChat?: unknown;
};

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as LegacyPrefs;
    const ver = parsed.prefsVersion ?? 1;
    // One-time migration: bump anyone still on the legacy "warm" default
    // to the current default. Users who explicitly want warm can flip
    // back from Settings → Appearance.
    if (ver < 2 && parsed.palette === "warm") {
      parsed.palette = DEFAULT_PREFS.palette;
    }
    // v5 → v6: palette list trimmed from 8 → 4 (vercel/github/linear/
    // catppuccin retired). Migrate anyone parked on a dropped palette
    // back to the current default.
    if (ver < 6 && parsed.palette && RETIRED_PALETTES.has(parsed.palette)) {
      parsed.palette = DEFAULT_PREFS.palette;
    }
    Reflect.deleteProperty(parsed, "material");
    Reflect.deleteProperty(parsed, "glass");
    Reflect.deleteProperty(parsed, "showReasoningInChat");
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
