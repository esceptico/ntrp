import { useState } from "react";
import clsx from "clsx";
import { useStore } from "../../store";
import type { GlassParams, GlassVariantId } from "../../store";
import { DEFAULT_GLASS_PREFS } from "../../store/prefs";
import { RangeField } from "./RangeField";

const VARIANTS: { id: GlassVariantId; label: string; desc: string }[] = [
  { id: "frosted", label: "Frosted", desc: "Default — readable foreground, lively background." },
  { id: "heavy", label: "Heavy", desc: "Focused-attention popovers; thicker material, stronger blur." },
  { id: "static", label: "Static", desc: "Solid surface, no blur. Use when backdrop bleed-through hurts." },
  { id: "clear", label: "Clear", desc: "Minimal material; near-transparent." },
  { id: "smoke", label: "Smoke", desc: "Always-dark glass; ignores theme. For high-contrast over photo/video." },
  { id: "milk", label: "Milk", desc: "Content-safe tier between Frosted and Static." },
];

export function GlassTab() {
  const glass = useStore((s) => s.prefs.glass);
  const setPref = useStore((s) => s.setPref);
  const [selected, setSelected] = useState<GlassVariantId>("frosted");

  function update(variant: GlassVariantId, patch: Partial<GlassParams>): void {
    setPref("glass", {
      ...glass,
      [variant]: { ...glass[variant], ...patch },
    });
  }

  function resetVariant(variant: GlassVariantId): void {
    setPref("glass", { ...glass, [variant]: DEFAULT_GLASS_PREFS[variant] });
  }

  function resetAll(): void {
    setPref("glass", DEFAULT_GLASS_PREFS);
  }

  const variant = VARIANTS.find((v) => v.id === selected)!;
  const params = glass[selected];

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[520px]">
          Tune each glass material independently. Changes apply live to every
          surface using that variant — including this settings window itself.
        </p>
        <button
          type="button"
          onClick={resetAll}
          className="text-xs font-medium text-muted hover:text-ink transition-colors"
        >
          Reset all
        </button>
      </div>

      <div className="grid grid-cols-[180px_minmax(0,1fr)] gap-4">
        {/* Left rail — variant picker */}
        <ul className="m-0 p-0 list-none grid gap-1">
          {VARIANTS.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                onClick={() => setSelected(v.id)}
                data-active={v.id === selected ? "true" : undefined}
                className={clsx(
                  "w-full text-left px-3 py-2 rounded-md transition-colors",
                  v.id === selected
                    ? "bg-surface-soft text-ink"
                    : "text-ink-soft hover:bg-surface-soft/60 hover:text-ink",
                )}
              >
                <div className="flex items-center gap-2.5">
                  <span
                    className={`glass-surface glass-${v.id} glass-radius-sm`}
                    style={{ width: 28, height: 18, borderRadius: 6 }}
                    aria-hidden
                  />
                  <span className="text-sm font-medium">{v.label}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>

        {/* Right pane — controls + preview */}
        <div className="grid gap-4">
          <div className="flex items-baseline justify-between gap-2">
            <div>
              <h3 className="m-0 text-base font-medium text-ink">{variant.label}</h3>
              <p className="m-0 mt-0.5 text-xs text-faint leading-[1.4]">{variant.desc}</p>
            </div>
            <button
              type="button"
              onClick={() => resetVariant(selected)}
              className="text-xs font-medium text-muted hover:text-ink transition-colors"
            >
              Reset
            </button>
          </div>

          {/* Live preview tile */}
          <GlassPreview variant={selected} />

          {/* Sliders */}
          <div className="grid gap-3">
            <RangeField
              label="Tint"
              value={params.tint}
              onChange={(v) => update(selected, { tint: v })}
              min={0}
              max={100}
              unit="%"
            />
            <RangeField
              label="Blur"
              value={params.blur}
              onChange={(v) => update(selected, { blur: v })}
              min={0}
              max={60}
              unit="px"
            />
            <RangeField
              label="Saturate"
              value={params.saturate}
              onChange={(v) => update(selected, { saturate: v })}
              min={0}
              max={250}
              unit="%"
            />
            <RangeField
              label="Rim"
              value={params.rim}
              onChange={(v) => update(selected, { rim: v })}
              min={0}
              max={100}
              unit="%"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Live preview tile. A glass card sits over a constrained "busy backdrop"
 *  (mesh gradient + a single line of scrolling text) so the user can see
 *  exactly what their adjustments do without leaving Settings. */
function GlassPreview({ variant }: { variant: GlassVariantId }) {
  return (
    <div
      className="relative overflow-hidden rounded-[12px] border border-line-soft"
      style={{ height: 160 }}
    >
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(at 15% 30%, #ff3b8d 0px, transparent 45%),
            radial-gradient(at 85% 25%, #6a5af9 0px, transparent 45%),
            radial-gradient(at 70% 80%, #00d4ff 0px, transparent 45%),
            radial-gradient(at 25% 75%, #ffa84d 0px, transparent 45%),
            #08081a
          `,
        }}
        aria-hidden
      />
      <div
        className="absolute inset-0 flex items-center"
        style={{
          fontFamily: "'Times New Roman', serif",
          fontSize: 96,
          fontWeight: 700,
          color: "rgba(255,255,255,0.6)",
          letterSpacing: "-0.04em",
          whiteSpace: "nowrap",
          mixBlendMode: "overlay",
        }}
        aria-hidden
      >
        <span style={{ animation: "glassPreviewScroll 22s linear infinite" }}>
          DESIGN · GLASS · LIGHT · DESIGN · GLASS · LIGHT ·{" "}
        </span>
      </div>
      <div
        className={`glass-surface glass-${variant}`}
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: 240,
          height: 100,
          borderRadius: 16,
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
