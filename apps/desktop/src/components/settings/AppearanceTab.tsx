import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { ArrowUp, Check, ChevronDown, Keyboard, Monitor, Moon, RotateCcw, Sun, type LucideIcon } from "lucide-react";
import {
  DEFAULT_QUICK_CAPTURE_SHORTCUT,
  useStore,
  type Material,
  type PaletteId,
  type ThemeChoice,
  type ThinkingAnimation,
  type ThinkingIntensity,
} from "../../store";
import { DEFAULT_GLASS_PREFS } from "../../store/prefs";
import { PALETTES, PALETTE_BY_ID, type PaletteMeta, type PaletteSwatch } from "../../lib/palettes";
import { eventToAccelerator, formatAccelerator } from "../../lib/accelerator";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { GlassToggle } from "../GlassToggle";
import { GlassSwitch } from "../GlassSwitch";

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
  const glass = useStore((s) => s.prefs.glass);
  const material = useStore((s) => s.prefs.material);
  const setPref = useStore((s) => s.setPref);
  const isGlass = material === "glass";

  return (
    <div className="grid gap-6">
      <section className="surface-rail divide-y divide-line-soft/50">
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
      </section>

      <section className="surface-rail divide-y divide-line-soft/50">
        <SettingRow
          title="Quick capture shortcut"
          hint="Global hotkey to summon the floating composer from anywhere. Enter creates a new session and sends the message."
          control={<ShortcutRecorder />}
        />
      </section>

      <section className="surface-rail divide-y divide-line-soft/50">
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

      {/* === Material ===
          Same .glass-surface CSS class, two recipes swapped via
          :root[data-material]. Glass = translucent + backdrop-filter
          (Tint/Blur/Saturate apply). Linen = solid + hairline ring +
          drop shadow (only Rim applies). Sliders are only rendered
          when they have effect — no dimmed dead UI. */}
      <section className="surface-rail divide-y divide-line-soft/50">
        <SettingRow
          title="Glass material"
          hint="Translucent surfaces with backdrop blur. Off = Linen — solid panels with a hairline ring."
          control={
            <GlassSwitch
              size="sm"
              checked={isGlass}
              onChange={(next) => setPref("material", (next ? "glass" : "linen") as Material)}
              aria-label="Use glass material"
            />
          }
        />
        {isGlass && (
          <>
            <SliderRow
              title="Tint"
              hint="Opacity of the surface color over the backdrop."
              value={glass.tint}
              min={0}
              max={100}
              unit="%"
              onChange={(v) => setPref("glass", { ...glass, tint: v })}
            />
            <SliderRow
              title="Blur"
              hint="Backdrop blur radius (capped at 18px — two glass layers can stack at runtime; per-layer must stay under 20px per glass-design.md)."
              value={glass.blur}
              min={0}
              max={18}
              unit="px"
              onChange={(v) => setPref("glass", { ...glass, blur: v })}
            />
            <SliderRow
              title="Saturate"
              hint="Color intensity pulled from behind the surface."
              value={glass.saturate}
              min={0}
              max={250}
              unit="%"
              onChange={(v) => setPref("glass", { ...glass, saturate: v })}
            />
          </>
        )}
        <SliderRow
          title="Rim"
          hint="Top-edge specular highlight strength."
          value={glass.rim}
          min={0}
          max={100}
          unit="%"
          onChange={(v) => setPref("glass", { ...glass, rim: v })}
        />
        <div className="px-4 py-2.5 flex justify-end">
          <button
            type="button"
            onClick={() => {
              setPref("glass", DEFAULT_GLASS_PREFS);
              setPref("material", "linen");
            }}
            className="text-xs font-medium text-muted hover:text-ink transition-colors"
          >
            Reset to defaults
          </button>
        </div>
      </section>
    </div>
  );
}

/** Slider in a SettingRow's control slot — title/hint live on the row
 *  (matches every other Appearance row), so the slider itself is just
 *  the input + value readout. Fixed-width track keeps the right edge
 *  aligned across rows. */
function SliderRow({
  title,
  hint,
  value,
  min,
  max,
  unit,
  onChange,
}: {
  title: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (next: number) => void;
}) {
  return (
    <SettingRow
      title={title}
      hint={hint}
      control={
        <div className="flex items-center gap-3 w-[220px]">
          <input
            type="range"
            value={value}
            min={min}
            max={max}
            onChange={(e) => onChange(Number(e.target.value))}
            className="flex-1 accent-accent cursor-pointer"
          />
          <span className="w-12 text-right text-sm text-ink-soft tabular-nums font-mono">
            {Math.round(value)}{unit}
          </span>
        </div>
      }
    />
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
          <IconButton
            size="lg"
            tone="faint"
            className="rounded-[8px]"
            onClick={() => void reset()}
            aria-label="Reset to default"
            title="Reset to default"
          >
            <RotateCcw size={ICON.SM} strokeWidth={2} />
          </IconButton>
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
      className="grid place-items-center w-[22px] h-[22px] rounded-md text-xs font-semibold shrink-0 border border-line"
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
            className="glass-surface surface-popover fixed z-[60] py-1"
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
