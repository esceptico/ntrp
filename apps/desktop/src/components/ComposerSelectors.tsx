import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { updateServerConfig, fetchServerConfig } from "../actions";

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  openrouter: "OpenRouter",
  xai: "xAI",
  custom: "Custom",
};

/** Strip `provider/` prefix so the chip stays compact. */
function shortModelLabel(model: string): string {
  const slash = model.lastIndexOf("/");
  return slash >= 0 ? model.slice(slash + 1) : model;
}

function useOutsideClick(
  ref: React.RefObject<HTMLElement | null>,
  open: boolean,
  onClose: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, ref, onClose]);
}

/** Combined model + reasoning chip used at the right edge of the composer. */
export function ModelReasoningChip() {
  const cfg = useStore((s) => s.serverConfig);
  const models = useStore((s) => s.serverModels);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  useOutsideClick(wrapRef, open, () => setOpen(false));

  const groups = useMemo(() => {
    if (!models) return [];
    return models.groups.length > 0
      ? models.groups
      : [{ provider: "all", models: models.models }];
  }, [models]);

  const filteredGroups = useMemo(() => {
    if (!query.trim()) return groups;
    const q = query.toLowerCase();
    return groups
      .map((g) => ({ ...g, models: g.models.filter((m) => m.toLowerCase().includes(q)) }))
      .filter((g) => g.models.length > 0);
  }, [groups, query]);

  if (!cfg) return null;
  const currentModel = cfg.chat_model;
  const efforts = cfg.reasoning_efforts;
  const currentEffort = cfg.reasoning_effort;
  const modelReasoningEfforts = cfg.model_reasoning_efforts;

  const apply = async (patch: Record<string, unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await updateServerConfig(patch);
    } catch {
      await fetchServerConfig();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={busy || !models}
        title={efforts.length > 0 ? `${currentModel} · thinking ${currentEffort ?? "off"}` : currentModel}
        className={clsx(
          "inline-flex items-center gap-1.5 h-7 pl-2.5 pr-2 rounded-full text-[11.5px] font-medium tracking-[-0.005em] transition-colors select-none max-w-[260px]",
          open
            ? "bg-surface-soft text-ink"
            : "text-muted hover:bg-surface-soft hover:text-ink",
        )}
      >
        <span className="truncate font-mono text-[11px] text-ink-soft">{shortModelLabel(currentModel)}</span>
        {efforts.length > 0 && (
          <>
            <span className="text-whisper">·</span>
            <span className="text-faint">{currentEffort ?? "off"}</span>
          </>
        )}
        <ChevronDown size={11} strokeWidth={1.8} className="shrink-0 opacity-70" />
      </button>

      {open && models && (
        <div className="absolute bottom-[calc(100%+6px)] right-0 z-30 w-[300px] rounded-[12px] border border-line-soft bg-surface shadow-[var(--shadow-pop)] overflow-hidden">
          {efforts.length > 0 && (
            <div className="grid gap-1 px-3 pt-2.5 pb-2 border-b border-line-soft">
              <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-faint">
                Thinking for this model
              </div>
              <div className="flex flex-wrap gap-1">
                <EffortPill
                  label="off"
                  active={currentEffort === null}
                  onClick={() => void apply({ reasoning_effort: null })}
                />
                {efforts.map((eff) => (
                  <EffortPill
                    key={eff}
                    label={eff}
                    active={currentEffort === eff}
                    onClick={() => void apply({ reasoning_effort: eff })}
                  />
                ))}
              </div>
            </div>
          )}
          <div className="grid">
            <input
              type="text"
              placeholder="Search models…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full h-8 px-3 border-0 border-b border-line-soft bg-transparent text-[12.5px] text-ink outline-none placeholder:text-whisper"
              autoFocus
            />
            <div className="max-h-[260px] overflow-y-auto scroll-thin py-1">
              {filteredGroups.length === 0 && (
                <div className="px-3 py-2 text-[12px] text-faint italic">No matches.</div>
              )}
              {filteredGroups.map((g) => (
                <div key={g.provider}>
                  {groups.length > 1 && (
                    <div className="px-3 pt-2 pb-1 text-[10px] font-medium uppercase tracking-[0.08em] text-faint select-none">
                      {PROVIDER_LABELS[g.provider] ?? g.provider}
                    </div>
                  )}
                  {g.models.map((m) => {
                    const isCurrent = m === currentModel;
                    const savedEffort = modelReasoningEfforts[m];
                    return (
                      <button
                        key={m}
                        type="button"
                        onClick={() => {
                          if (m !== currentModel) void apply({ chat_model: m });
                          setQuery("");
                        }}
                        className={clsx(
                          "w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12px] font-mono transition-colors",
                          isCurrent ? "text-ink" : "text-ink-soft hover:bg-surface-soft/60",
                        )}
                      >
                        <span className="grid place-items-center w-3 h-3 shrink-0">
                          {isCurrent && <Check size={11} strokeWidth={2.4} className="text-accent" />}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{m}</span>
                        {savedEffort && (
                          <span className="shrink-0 text-[11px] font-sans text-faint">
                            {savedEffort}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EffortPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "h-6 px-2 rounded-full text-[11px] font-medium tracking-[-0.005em] transition-colors select-none capitalize",
        active
          ? "bg-accent-soft text-accent-strong"
          : "text-muted hover:bg-surface-soft hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}
