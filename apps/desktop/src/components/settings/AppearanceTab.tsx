import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { ArrowUp, Check, ChevronDown, Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import {
  useStore,
  type PaletteId,
  type ThemeChoice,
  type ThinkingAnimation,
  type ThinkingIntensity,
} from "../../store";
import { PALETTES, PALETTE_BY_ID, type PaletteMeta, type PaletteSwatch } from "../../lib/palettes";

const VARIANTS: { id: ThinkingAnimation; label: string; hint: string }[] = [
  { id: "comet", label: "Comet", hint: "Single arc travels around the rim" },
  { id: "breath", label: "Breath", hint: "Wide diffuse halo that breathes slowly" },
  { id: "hue-cycle", label: "Border tint", hint: "Border color drifts toward accent — no motion" },
  { id: "send-orbit", label: "Send orbit", hint: "Spinner around the send button only" },
];

const THEMES: { id: ThemeChoice; label: string; icon: LucideIcon }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

const INTENSITIES: { id: ThinkingIntensity; label: string }[] = [
  { id: "subtle", label: "Subtle" },
  { id: "normal", label: "Normal" },
  { id: "strong", label: "Strong" },
];

export function AppearanceTab() {
  const thinking = useStore((s) => s.prefs.thinkingAnimation);
  const intensity = useStore((s) => s.prefs.thinkingIntensity);
  const theme = useStore((s) => s.prefs.theme);
  const palette = useStore((s) => s.prefs.palette);
  const setPref = useStore((s) => s.setPref);

  return (
    <div className="grid gap-6">
      <section className="rounded-[12px] border border-line-soft bg-bg-main/30 overflow-hidden">
        <SettingRow
          title="Mode"
          hint="Light, Dark, or follow your system preference."
          control={
            <div className="inline-flex p-0.5 rounded-[9px] bg-surface-soft">
              {THEMES.map((t) => {
                const Icon = t.icon;
                const active = theme === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setPref("theme", t.id)}
                    className={clsx(
                      "inline-flex items-center gap-1.5 h-7 px-3 rounded-[7px] text-[12px] font-medium tracking-[-0.005em] transition-colors",
                      active
                        ? "bg-surface text-ink shadow-[var(--shadow-sm)]"
                        : "text-muted hover:text-ink",
                    )}
                  >
                    <Icon size={12} strokeWidth={1.7} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          }
        />
        <div className="border-t border-line-soft" />
        <SettingRow
          title="Palette"
          hint="Color scheme used across the app."
          control={<PalettePicker value={palette} onChange={(id) => setPref("palette", id)} />}
        />
      </section>

      <section className="rounded-[12px] border border-line-soft bg-bg-main/30 overflow-hidden">
        <SettingRow
          title="Thinking indicator"
          hint="Shown on the composer while the agent is running but has not yet streamed its first token."
          control={
            <SegmentedControl
              value={intensity}
              options={INTENSITIES}
              onChange={(id) => setPref("thinkingIntensity", id)}
            />
          }
        />
        <div className="border-t border-line-soft" />
        <div className="px-4 py-4 grid grid-cols-2 gap-2">
          {VARIANTS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setPref("thinkingAnimation", v.id)}
              className={clsx(
                "group flex flex-col gap-2 p-3 rounded-[10px] border text-left transition-colors",
                thinking === v.id
                  ? "border-line-strong bg-surface-soft/60"
                  : "border-line-soft bg-bg-main/30 hover:bg-surface-soft/40",
              )}
            >
              <Preview variant={v.id} intensity={intensity} />
              <div className="grid gap-0.5">
                <div className="text-[12.5px] font-medium text-ink tracking-[-0.005em]">
                  {v.label}
                </div>
                <div className="text-[11.5px] text-faint leading-snug">{v.hint}</div>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function SettingRow({
  title,
  hint,
  control,
}: {
  title: string;
  hint: string;
  control: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-ink tracking-[-0.005em]">{title}</div>
        <div className="text-[12px] text-muted mt-0.5 leading-snug">{hint}</div>
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex p-0.5 rounded-[9px] bg-surface-soft">
      {options.map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            className={clsx(
              "inline-flex items-center justify-center h-7 px-3 rounded-[7px] text-[12px] font-medium tracking-[-0.005em] transition-colors",
              active
                ? "bg-surface text-ink shadow-[var(--shadow-sm)]"
                : "text-muted hover:text-ink",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/** Swatch chip used both as the dropdown trigger's icon and per-row icon
 *  inside the popover. Renders an "Aa" in the palette's accent color over
 *  the palette's background. */
function PaletteIcon({ swatch }: { swatch: PaletteSwatch }) {
  return (
    <span
      aria-hidden
      className="grid place-items-center w-[22px] h-[22px] rounded-md text-[11px] font-semibold shrink-0 border border-[rgba(0,0,0,0.06)]"
      style={{ background: swatch.bg, color: swatch.accent }}
    >
      Aa
    </span>
  );
}

function PalettePicker({
  value,
  onChange,
}: {
  value: PaletteId;
  onChange: (id: PaletteId) => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const current = PALETTE_BY_ID[value];
  // The trigger swatch reflects the active resolved scheme so it matches
  // what the user sees rendered. Listen for OS-level changes when the
  // theme is set to "system" so the swatch flips with the OS.
  const theme = useStore((s) => s.prefs.theme);
  const isDark = useResolvedDark(theme);
  const triggerSwatch = isDark ? current.dark : current.light;

  // Anchor the portaled popover to the trigger's bounding rect.
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 6, left: rect.left, width: Math.max(rect.width, 200) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 h-8 pl-1.5 pr-2 rounded-[8px] border border-line-soft bg-surface hover:bg-surface-soft/60 transition-colors text-[12.5px] font-medium text-ink-soft"
      >
        <PaletteIcon swatch={triggerSwatch} />
        <span>{current.label}</span>
        <ChevronDown size={12} strokeWidth={1.8} className="opacity-70" />
      </button>
      {open && pos &&
        createPortal(
          <div
            ref={popoverRef}
            style={{ top: pos.top, left: pos.left, width: pos.width }}
            className="fixed z-[60] py-1 rounded-[10px] border border-line-soft bg-surface shadow-[var(--shadow-pop)]"
          >
            {PALETTES.map((p) => (
              <PaletteRow
                key={p.id}
                palette={p}
                dark={isDark}
                active={p.id === value}
                onClick={() => {
                  onChange(p.id);
                  setOpen(false);
                }}
              />
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

function PaletteRow({
  palette,
  dark,
  active,
  onClick,
}: {
  palette: PaletteMeta;
  dark: boolean;
  active: boolean;
  onClick: () => void;
}) {
  const swatch = dark ? palette.dark : palette.light;
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "w-full flex items-center gap-2.5 px-2.5 py-1.5 text-left transition-colors",
        active ? "bg-surface-soft" : "hover:bg-surface-soft/60",
      )}
    >
      <PaletteIcon swatch={swatch} />
      <span className="text-[12.5px] text-ink flex-1">{palette.label}</span>
      {active && <Check size={12} strokeWidth={2} className="text-accent-strong" />}
    </button>
  );
}

function useResolvedDark(theme: ThemeChoice): boolean {
  const [systemDark, setSystemDark] = useState(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemDark(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return systemDark;
}

/** Mini composer-shaped box that runs the variant continuously so the
 *  user can compare them side-by-side without leaving Settings. */
function Preview({
  variant,
  intensity,
}: {
  variant: ThinkingAnimation;
  intensity: ThinkingIntensity;
}) {
  return (
    <div
      className="composer-card relative h-[44px] rounded-[10px] border border-line bg-surface flex items-center pl-3 pr-1.5"
      data-thinking="true"
      data-thinking-style={variant}
      data-thinking-intensity={intensity}
    >
      <span className="text-[11.5px] text-faint flex-1">Ask anything…</span>
      <span
        data-send="true"
        className="grid place-items-center w-6 h-6 rounded-full bg-ink text-on-ink shrink-0"
      >
        <ArrowUp size={11} strokeWidth={2.4} />
      </span>
    </div>
  );
}
