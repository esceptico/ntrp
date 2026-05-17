import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { ArrowUp, Check, ChevronDown, Keyboard, Monitor, Moon, RotateCcw, Sun, type LucideIcon } from "lucide-react";
import {
  DEFAULT_QUICK_CAPTURE_SHORTCUT,
  useStore,
  type PaletteId,
  type ThemeChoice,
  type ThinkingAnimation,
  type ThinkingIntensity,
} from "../../store";
import { DEFAULT_GLASS_PREFS } from "../../store/prefs";
import { PALETTES, PALETTE_BY_ID, type PaletteMeta, type PaletteSwatch } from "../../lib/palettes";
import { eventToAccelerator, formatAccelerator } from "../../lib/accelerator";
import { ICON } from "../../lib/icons";
import { GlassToggle } from "../GlassToggle";
import { GlassSwitch } from "../GlassSwitch";
import { RangeField } from "./RangeField";

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
  const showReasoning = useStore((s) => s.prefs.showReasoningInChat);
  const glass = useStore((s) => s.prefs.glass);
  const setPref = useStore((s) => s.setPref);

  return (
    <div className="grid gap-6">
      <section className="rounded-[12px] border border-line-soft bg-bg-main/30 overflow-hidden divide-y divide-line-soft/50">
        <SettingRow
          title="Mode"
          hint="Light, Dark, or follow your system preference."
          control={
            <GlassToggle
              size="sm"
              value={theme}
              onChange={(v) => setPref("theme", v as ThemeChoice)}
              options={THEMES.map((t) => ({
                value: t.id,
                label: t.label,
                icon: <t.icon size={ICON.MD} strokeWidth={2} />,
              }))}
            />
          }
        />
        <SettingRow
          title="Palette"
          hint="Color scheme used across the app."
          control={<PalettePicker value={palette} onChange={(id) => setPref("palette", id)} />}
        />
        <SettingRow
          title="Reasoning in chat"
          hint="Show or hide reasoning rows. Tool calls stay visible."
          control={
            <GlassSwitch
              size="sm"
              checked={showReasoning}
              onChange={(next) => setPref("showReasoningInChat", next)}
              aria-label="Show reasoning in chat"
            />
          }
        />
      </section>

      <section className="rounded-[12px] border border-line-soft bg-bg-main/30 overflow-hidden divide-y divide-line-soft/50">
        <SettingRow
          title="Quick capture shortcut"
          hint="Global hotkey to summon the floating composer from anywhere. Enter creates a new session and sends the message."
          control={<ShortcutRecorder />}
        />
      </section>

      <section className="rounded-[12px] border border-line-soft bg-bg-main/30 overflow-hidden divide-y divide-line-soft/50">
        <SettingRow
          title="Thinking indicator"
          hint="Shown on the composer while the agent is running but has not yet streamed its first token."
          control={
            <GlassToggle
              size="sm"
              value={intensity}
              onChange={(v) => setPref("thinkingIntensity", v as ThinkingIntensity)}
              options={INTENSITIES.map((o) => ({ value: o.id, label: o.label }))}
            />
          }
        />
        <div className="px-4 py-4 grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-2">
          {VARIANTS.map((v) => (
            <VariantCard
              key={v.id}
              variant={v}
              intensity={intensity}
              selected={thinking === v.id}
              onSelect={() => setPref("thinkingAnimation", v.id)}
            />
          ))}
        </div>
      </section>

      {/* === Glass ===
          Per the consolidation pass, glass is one canonical material now;
          these four knobs tune it everywhere it appears across the app. */}
      <section className="grid gap-3">
        <div className="flex items-baseline justify-between">
          <div>
            <h3 className="m-0 text-sm font-medium text-ink">Glass</h3>
            <p className="m-0 mt-0.5 text-xs text-faint leading-[1.4]">
              Tune the frosted material used across every glass surface. Changes apply live.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setPref("glass", DEFAULT_GLASS_PREFS)}
            className="text-xs font-medium text-muted hover:text-ink transition-colors"
          >
            Reset
          </button>
        </div>

        <GlassPreview />

        <div className="grid gap-2.5">
          <RangeField
            label="Tint"
            value={glass.tint}
            onChange={(v) => setPref("glass", { ...glass, tint: v })}
            min={0} max={100} unit="%"
          />
          <RangeField
            label="Blur"
            value={glass.blur}
            onChange={(v) => setPref("glass", { ...glass, blur: v })}
            min={0} max={60} unit="px"
          />
          <RangeField
            label="Saturate"
            value={glass.saturate}
            onChange={(v) => setPref("glass", { ...glass, saturate: v })}
            min={0} max={250} unit="%"
          />
          <RangeField
            label="Rim"
            value={glass.rim}
            onChange={(v) => setPref("glass", { ...glass, rim: v })}
            min={0} max={100} unit="%"
          />
        </div>
      </section>
    </div>
  );
}

/** Calm static gradient backdrop with one glass card centered. No motion,
 *  no text — gives blur/saturate something to chew without distracting
 *  from the slider feedback. */
function GlassPreview() {
  // The glass card spans most of the preview so the colored content sits
  // BEHIND it — that's the only way tint/saturate/blur do visible work.
  // A strip of raw content peeks above and below the card so you can
  // compare "raw" vs "through glass" at a glance.
  //   • tint:     mixes white into the cream/accent-soft gradient
  //   • blur:     smears the bars + accent badge
  //   • saturate: pumps the accent gradient + badge color
  //   • rim:      visible against the ink-tone bars behind the card
  return (
    <div
      className="relative overflow-hidden rounded-[10px] border border-line-soft"
      style={{ height: 180 }}
    >
      {/* Diagonal theme-color gradient — actual hue for saturate to pump. */}
      <div
        className="absolute inset-0"
        aria-hidden
        style={{
          background:
            "linear-gradient(135deg, var(--color-surface-sunken) 0%, var(--color-bg) 35%, var(--color-accent-soft) 100%)",
        }}
      />

      {/* Fake chat content — bars span full width so they extend behind
          the glass card AND show on the strips above/below it. */}
      <div aria-hidden className="absolute inset-0 px-4 py-3 grid gap-2 content-center">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-accent shrink-0" />
          <div className="h-2 flex-1 rounded bg-ink/55" />
        </div>
        <div className="h-2 w-full rounded bg-ink/35" />
        <div className="flex items-center gap-2">
          <span className="inline-flex h-5 items-center px-2 rounded-full bg-accent-soft text-accent-strong text-[10px] font-medium shrink-0">
            running
          </span>
          <div className="h-2 flex-1 rounded bg-ink/40" />
        </div>
        <div className="h-2 w-full rounded bg-ink/30" />
        <div className="h-2 w-3/4 rounded bg-ink/25" />
      </div>

      {/* Glass card overlays the middle band — content is right behind it,
          and a strip of raw content peeks at top + bottom. */}
      <div
        className="glass-surface"
        style={{
          position: "absolute",
          top: 32,
          bottom: 32,
          left: 16,
          right: 16,
          display: "grid",
          placeItems: "center",
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        Preview surface
      </div>
    </div>
  );
}

/** Click-to-record input for the global quick-capture shortcut.
 *
 *  Crucial detail: globally-registered chords are intercepted by the OS
 *  *before* the renderer gets a keydown event. If we left the current
 *  chord bound while recording, the user couldn't press it (or any
 *  other already-bound chord) — the keystroke would summon the quick
 *  window instead of reaching our handler. So we explicitly unregister
 *  during the recording window, then re-register either the new chord
 *  (on success) or the previous one (on cancel / failure). */
function ShortcutRecorder() {
  const value = useStore((s) => s.prefs.quickCaptureShortcut);
  const setPref = useStore((s) => s.setPref);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!recording) return;

    // Snapshot the chord at record-start so cancel/cleanup can always
    // restore it even if the user changes the store mid-recording
    // (shouldn't happen, but defensive).
    const previous = value;
    let bound = false;

    // Unregister so the OS-level handler doesn't eat the chord we're
    // trying to record.
    void window.ntrpDesktop?.quickCapture?.setShortcut?.("");

    const handler = async (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      // Escape cancels without binding anything.
      if (event.key === "Escape") {
        setRecording(false);
        return;
      }
      const accelerator = eventToAccelerator(event);
      if (!accelerator) return; // modifier-only or unsupported key — wait
      const ok = await window.ntrpDesktop?.quickCapture?.setShortcut?.(accelerator);
      if (ok) {
        bound = true;
        setPref("quickCaptureShortcut", accelerator);
        setError(null);
      } else {
        setError(`'${formatAccelerator(accelerator)}' is already in use by another app.`);
      }
      setRecording(false);
    };
    window.addEventListener("keydown", handler, true);

    return () => {
      window.removeEventListener("keydown", handler, true);
      // If we didn't successfully bind a new chord, put the previous
      // one back so the user isn't left with no shortcut at all.
      if (!bound) void window.ntrpDesktop?.quickCapture?.setShortcut?.(previous);
    };
    // value is captured via `previous`; intentionally only re-running
    // when recording flips so we don't re-snapshot mid-recording.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording]);

  const reset = async () => {
    const ok = await window.ntrpDesktop?.quickCapture?.setShortcut?.(DEFAULT_QUICK_CAPTURE_SHORTCUT);
    if (ok) {
      setPref("quickCaptureShortcut", DEFAULT_QUICK_CAPTURE_SHORTCUT);
      setError(null);
    } else {
      setError(`'${formatAccelerator(DEFAULT_QUICK_CAPTURE_SHORTCUT)}' is already in use.`);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="inline-flex items-center gap-1.5">
        <button
          ref={ref}
          type="button"
          onClick={() => setRecording((r) => !r)}
          className={clsx(
            "inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[8px] border text-sm font-medium tracking-[-0.005em] tabular-nums transition-colors min-w-[140px] justify-center",
            recording
              ? "border-accent bg-accent-soft text-accent-strong"
              : "border-line-soft bg-surface text-ink-soft hover:bg-surface-soft/60",
          )}
        >
          <Keyboard size={ICON.SM} strokeWidth={2} className="opacity-70" />
          {recording ? "Press chord…" : (value ? formatAccelerator(value) : "Disabled")}
        </button>
        {value !== DEFAULT_QUICK_CAPTURE_SHORTCUT && (
          <button
            type="button"
            onClick={() => void reset()}
            aria-label="Reset to default"
            title="Reset to default"
            className="grid place-items-center w-8 h-8 rounded-[8px] text-faint hover:text-ink hover:bg-surface-soft transition-colors"
          >
            <RotateCcw size={ICON.SM} strokeWidth={2} />
          </button>
        )}
      </div>
      {error && (
        <span className="text-xs text-bad text-right max-w-[260px]">{error}</span>
      )}
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
    <div className="flex flex-col items-start gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <div className="text-base font-medium text-ink tracking-[-0.005em]">{title}</div>
        <div className="text-sm text-muted mt-0.5 leading-snug">{hint}</div>
      </div>
      <div className="shrink-0 max-w-full">{control}</div>
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
      className="grid place-items-center w-[22px] h-[22px] rounded-md text-xs font-semibold shrink-0 border border-[rgba(0,0,0,0.06)]"
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
        className="inline-flex items-center gap-2 h-8 pl-1.5 pr-2 rounded-[8px] border border-line-soft bg-surface hover:bg-surface-soft/60 transition-colors text-sm font-medium text-ink-soft"
      >
        <PaletteIcon swatch={triggerSwatch} />
        <span>{current.label}</span>
        <ChevronDown size={ICON.MD} strokeWidth={2} className="opacity-70" />
      </button>
      {open && pos &&
        createPortal(
          <div
            ref={popoverRef}
            style={{ top: pos.top, left: pos.left, width: pos.width }}
            className="glass-surface glass-radius-sm fixed z-[60] py-1"
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
      data-active={active ? "true" : undefined}
      className="app-row w-full flex items-center gap-2.5 px-2.5 py-1.5 text-ink-soft text-left"
    >
      <PaletteIcon swatch={swatch} />
      <span className="text-sm text-ink flex-1">{palette.label}</span>
      {active && <Check size={ICON.MD} strokeWidth={2} className="text-accent-strong" />}
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
/** Wraps a Preview with hover-driven animation gating. Animations only
 *  run when the variant is selected or its card is being hovered — five
 *  always-on Houdini / conic-gradient previews on every settings open
 *  was wasteful (each comet preview compositor-tickrates a registered
 *  custom property at 60fps). */
function VariantCard({
  variant,
  intensity,
  selected,
  onSelect,
}: {
  variant: { id: ThinkingAnimation; label: string; hint: string };
  intensity: ThinkingIntensity;
  selected: boolean;
  onSelect: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={clsx(
        "group flex flex-col gap-2 p-3 rounded-[10px] border text-left transition-colors",
        selected
          ? "border-line-strong bg-surface-soft/60"
          : "border-line-soft bg-bg-main/30 hover:bg-surface-soft/40",
      )}
    >
      <Preview variant={variant.id} intensity={intensity} animate={selected || hovered} />
      <div className="grid gap-0.5">
        <div className="text-sm font-medium text-ink tracking-[-0.005em]">
          {variant.label}
        </div>
        <div className="text-xs text-faint leading-snug">{variant.hint}</div>
      </div>
    </button>
  );
}

function Preview({
  variant,
  intensity,
  animate,
}: {
  variant: ThinkingAnimation;
  intensity: ThinkingIntensity;
  animate: boolean;
}) {
  return (
    <div
      className="composer-card relative h-[44px] rounded-[10px] border border-line bg-surface flex items-center pl-3 pr-1.5"
      data-thinking={animate ? "true" : undefined}
      data-thinking-style={variant}
      data-thinking-intensity={intensity}
    >
      <span className="text-xs text-faint flex-1">Ask anything…</span>
      <span
        data-send="true"
        className="grid place-items-center w-6 h-6 rounded-full bg-ink text-on-ink shrink-0"
      >
        <ArrowUp size={ICON.SM} strokeWidth={2.4} />
      </span>
    </div>
  );
}
