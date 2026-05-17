import { useStore } from "../../store";
import type { GlassParams } from "../../store";
import { DEFAULT_GLASS_PREFS } from "../../store/prefs";
import { RangeField } from "./RangeField";

export function GlassTab() {
  const glass = useStore((s) => s.prefs.glass);
  const setPref = useStore((s) => s.setPref);

  function update(patch: Partial<GlassParams>): void {
    setPref("glass", { ...glass, ...patch });
  }

  function resetAll(): void {
    setPref("glass", DEFAULT_GLASS_PREFS);
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[520px]">
          Tune the glass material. Changes apply live to every surface —
          including this settings window itself.
        </p>
        <button
          type="button"
          onClick={resetAll}
          className="text-xs font-medium text-muted hover:text-ink transition-colors"
        >
          Reset all
        </button>
      </div>

      <GlassPreview />

      <div className="grid gap-3">
        <RangeField
          label="Tint"
          value={glass.tint}
          onChange={(v) => update({ tint: v })}
          min={0}
          max={100}
          unit="%"
        />
        <RangeField
          label="Blur"
          value={glass.blur}
          onChange={(v) => update({ blur: v })}
          min={0}
          max={60}
          unit="px"
        />
        <RangeField
          label="Saturate"
          value={glass.saturate}
          onChange={(v) => update({ saturate: v })}
          min={0}
          max={250}
          unit="%"
        />
        <RangeField
          label="Rim"
          value={glass.rim}
          onChange={(v) => update({ rim: v })}
          min={0}
          max={100}
          unit="%"
        />
      </div>
    </div>
  );
}

/** Live preview tile. A glass card sits over a constrained "busy backdrop"
 *  (mesh gradient + a single line of scrolling text) so the user can see
 *  exactly what their adjustments do without leaving Settings. */
function GlassPreview() {
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
        className="glass-surface"
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
