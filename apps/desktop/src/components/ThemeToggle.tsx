import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { useStore } from "../store";
import { Tooltip } from "./ui/Tooltip";

/** Resolved light/dark, tracking the OS when the pref is "system". */
function useIsDark(): boolean {
  const theme = useStore((s) => s.prefs.theme);
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemDark(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);
  return theme === "dark" || (theme === "system" && systemDark);
}

// Eight sun rays, pre-computed so the markup stays declarative.
const RAYS = Array.from({ length: 8 }, (_, i) => {
  const a = (i * Math.PI) / 4;
  return {
    x1: 12 + Math.cos(a) * 7.5,
    y1: 12 + Math.sin(a) * 7.5,
    x2: 12 + Math.cos(a) * 10.5,
    y2: 12 + Math.sin(a) * 10.5,
  };
});

const SPRING = { type: "spring", stiffness: 240, damping: 20, mass: 0.9 } as const;

/**
 * Quick light/dark switch. The sun's rays retract and a masked circle slides
 * across to carve the body into a crescent moon — a genuine shape morph, not
 * an icon crossfade. Clicking re-themes the whole app.
 */
export function ThemeToggle() {
  const setPref = useStore((s) => s.setPref);
  const isDark = useIsDark();

  return (
    <Tooltip label={isDark ? "Switch to light" : "Switch to dark"}>
      <button
        type="button"
        aria-label="Toggle light and dark"
        onClick={() => setPref("theme", isDark ? "light" : "dark")}
        className="grid place-items-center w-8 h-8 shrink-0 rounded-lg text-muted hover:text-ink hover:bg-surface-soft/70 transition-[color,background-color,scale] duration-check ease-out active:scale-[0.92]"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
          <mask id="theme-moon-mask">
            <rect x="0" y="0" width="24" height="24" fill="white" />
            <motion.circle
              r="9"
              fill="black"
              initial={false}
              animate={{ cx: isDark ? 17 : 28, cy: isDark ? 7 : -4 }}
              transition={SPRING}
            />
          </mask>
          <motion.circle
            cx="12"
            cy="12"
            fill="currentColor"
            mask="url(#theme-moon-mask)"
            initial={false}
            animate={{ r: isDark ? 8 : 5 }}
            transition={SPRING}
          />
          <motion.g
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            initial={false}
            animate={{ opacity: isDark ? 0 : 1, scale: isDark ? 0.5 : 1, rotate: isDark ? -30 : 0 }}
            transition={SPRING}
            style={{ transformOrigin: "12px 12px" }}
          >
            {RAYS.map((r, i) => (
              <line key={i} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} />
            ))}
          </motion.g>
        </svg>
      </button>
    </Tooltip>
  );
}
