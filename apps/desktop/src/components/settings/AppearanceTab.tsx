import clsx from "clsx";
import { ArrowUp } from "lucide-react";
import { useStore, type ThinkingAnimation } from "../../store";

const VARIANTS: { id: ThinkingAnimation; label: string; hint: string }[] = [
  { id: "comet", label: "Comet", hint: "Single arc travels around the rim" },
  { id: "breath", label: "Breath", hint: "Wide diffuse halo that breathes slowly" },
  { id: "hue-cycle", label: "Border tint", hint: "Border color drifts toward accent — no motion" },
  { id: "send-orbit", label: "Send orbit", hint: "Spinner around the send button only" },
];

export function AppearanceTab() {
  const current = useStore((s) => s.prefs.thinkingAnimation);
  const setPref = useStore((s) => s.setPref);

  return (
    <div className="grid gap-4">
      <div>
        <h3 className="m-0 text-[12px] font-medium uppercase tracking-[0.06em] text-faint">
          Thinking indicator
        </h3>
        <p className="m-0 mt-1 text-[12.5px] text-muted leading-[1.45] max-w-[480px]">
          Shown on the composer while the agent is running but has not yet streamed its first
          token. Pick whichever feels right.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {VARIANTS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setPref("thinkingAnimation", v.id)}
            className={clsx(
              "group flex flex-col gap-2 p-3 rounded-[10px] border text-left transition-colors",
              current === v.id
                ? "border-line-strong bg-surface-soft/60"
                : "border-line-soft bg-bg-main/30 hover:bg-surface-soft/40",
            )}
          >
            <Preview variant={v.id} />
            <div className="grid gap-0.5">
              <div className="text-[12.5px] font-medium text-ink tracking-[-0.005em]">
                {v.label}
              </div>
              <div className="text-[11.5px] text-faint leading-snug">{v.hint}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Mini composer-shaped box that runs the variant continuously so the
 *  user can compare them side-by-side without leaving Settings. */
function Preview({ variant }: { variant: ThinkingAnimation }) {
  return (
    <div
      className="composer-card relative h-[44px] rounded-[10px] border border-line bg-surface flex items-center pl-3 pr-1.5"
      data-thinking="true"
      data-thinking-style={variant}
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
