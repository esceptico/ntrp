import clsx from "clsx";
import { ArrowUp, Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useStore, type ThemeChoice, type ThinkingAnimation } from "../../store";

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

export function AppearanceTab() {
  const thinking = useStore((s) => s.prefs.thinkingAnimation);
  const theme = useStore((s) => s.prefs.theme);
  const setPref = useStore((s) => s.setPref);

  return (
    <div className="grid gap-7">
      <section className="grid gap-3">
        <Header
          title="Theme"
          hint="Light, Dark, or follow your system preference."
        />
        <div className="inline-flex items-center gap-1 p-1 rounded-[10px] border border-line-soft bg-bg-main/30 self-start">
          {THEMES.map((t) => {
            const Icon = t.icon;
            const active = theme === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setPref("theme", t.id)}
                className={clsx(
                  "inline-flex items-center gap-1.5 h-8 px-3 rounded-[7px] text-[12.5px] font-medium tracking-[-0.005em] transition-colors",
                  active
                    ? "bg-surface text-ink shadow-[var(--shadow-sm)]"
                    : "text-muted hover:text-ink",
                )}
              >
                <Icon size={13} strokeWidth={1.7} />
                {t.label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="grid gap-3">
        <Header
          title="Thinking indicator"
          hint="Shown on the composer while the agent is running but has not yet streamed its first token."
        />
        <div className="grid grid-cols-2 gap-2">
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
      </section>
    </div>
  );
}

function Header({ title, hint }: { title: string; hint: string }) {
  return (
    <div>
      <h3 className="m-0 text-[12px] font-medium uppercase tracking-[0.06em] text-faint">
        {title}
      </h3>
      <p className="m-0 mt-1 text-[12.5px] text-muted leading-[1.45] max-w-[480px]">{hint}</p>
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
