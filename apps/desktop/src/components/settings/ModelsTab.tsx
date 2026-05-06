import { useMemo, useState } from "react";
import clsx from "clsx";
import { Check } from "lucide-react";
import { useStore } from "../../store";
import { updateServerConfig, fetchServerConfig } from "../../actions";
import type { ModelGroup } from "../../api";

type ModelKind = "chat_model" | "research_model" | "memory_model";

const KIND_LABELS: Record<ModelKind, { title: string; description: string }> = {
  chat_model: {
    title: "Agent",
    description: "Main conversation model used for chat.",
  },
  research_model: {
    title: "Research",
    description: "Used by research-style sub-agents and deeper investigations.",
  },
  memory_model: {
    title: "Memory",
    description: "Fact extraction and pattern consolidation.",
  },
};

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  openrouter: "OpenRouter",
  xai: "xAI",
  custom: "Custom",
};

export function ModelsTab() {
  const cfg = useStore((s) => s.serverConfig);
  const models = useStore((s) => s.serverModels);
  const [savingKind, setSavingKind] = useState<ModelKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!cfg || !models) {
    return <div className="text-[12.5px] text-faint">Loading models…</div>;
  }

  const groups: ModelGroup[] = models.groups.length > 0
    ? models.groups
    : [{ provider: "all", models: models.models }];

  return (
    <div className="grid gap-5">
      {(Object.keys(KIND_LABELS) as ModelKind[]).map((kind) => {
        const current = cfg[kind];
        const meta = KIND_LABELS[kind];
        return (
          <Section
            key={kind}
            title={meta.title}
            description={meta.description}
            current={current}
            saving={savingKind === kind}
            groups={groups}
            onSelect={async (model) => {
              if (model === current || savingKind) return;
              setSavingKind(kind);
              setError(null);
              try {
                await updateServerConfig({ [kind]: model });
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err));
                await fetchServerConfig();
              } finally {
                setSavingKind(null);
              }
            }}
          />
        );
      })}
      {error && (
        <div className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
          <strong className="text-bad text-[12px] font-semibold">Couldn't update model</strong>
          <span className="text-[12px] text-[#8a3220] leading-[1.4]">{error}</span>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  description,
  current,
  groups,
  saving,
  onSelect,
}: {
  title: string;
  description: string;
  current: string;
  groups: ModelGroup[];
  saving: boolean;
  onSelect: (model: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const filteredGroups = useMemo(() => {
    if (!query.trim()) return groups;
    const q = query.toLowerCase();
    return groups
      .map((g) => ({ ...g, models: g.models.filter((m) => m.toLowerCase().includes(q)) }))
      .filter((g) => g.models.length > 0);
  }, [groups, query]);

  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="grid gap-0.5">
          <div className="text-[13px] font-medium text-ink">{title}</div>
          <div className="text-[11.5px] text-faint leading-[1.4]">{description}</div>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={saving}
          className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md bg-surface border border-line text-ink-soft text-[12px] font-medium font-mono hover:border-line-strong transition-colors"
        >
          {saving ? "Saving…" : current || "—"}
        </button>
      </div>

      {open && (
        <div className="mt-1 rounded-[10px] border border-line-soft bg-surface-soft/40 overflow-hidden">
          <input
            type="text"
            placeholder="Search models…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full h-8 px-3 border-0 border-b border-line-soft bg-transparent text-[12.5px] text-ink outline-none placeholder:text-whisper"
            autoFocus
          />
          <div className="max-h-[280px] overflow-y-auto scroll-thin py-1">
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
                  const isCurrent = m === current;
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => {
                        onSelect(m);
                        setOpen(false);
                        setQuery("");
                      }}
                      className={clsx(
                        "w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12.5px] font-mono transition-colors",
                        isCurrent ? "text-ink" : "text-ink-soft hover:bg-surface/60",
                      )}
                    >
                      <span className="grid place-items-center w-3 h-3 shrink-0">
                        {isCurrent && <Check size={11} strokeWidth={2.4} className="text-accent" />}
                      </span>
                      <span className="truncate">{m}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
