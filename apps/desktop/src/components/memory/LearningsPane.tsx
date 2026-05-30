import { useCallback, useEffect, useState } from "react";

import {
  getLearnings,
  listLearnings,
  putLearnings,
  type LearningsAdjudicator,
} from "../../api/learnings";
import { useStore } from "../../store";
import { DetailPlaceholder, ListError } from "./shared";

const ADJUDICATORS: { id: LearningsAdjudicator; label: string; hint: string }[] = [
  { id: "dedup", label: "Dedup", hint: "what counts as a duplicate memory" },
  { id: "contradiction", label: "Contradiction", hint: "when one claim supersedes another" },
  { id: "entity_link", label: "Entity linking", hint: "which entity a memory belongs to" },
];

const PLACEHOLDER = "# No corrections yet\n\nEdit a decision in Memory (e.g. undo a contradiction, split an entity) and it shows up here. You can also hand-write house rules — this is just markdown the assistant honors.\n";

export function LearningsPane() {
  const config = useStore((s) => s.config);
  const [present, setPresent] = useState<LearningsAdjudicator[]>([]);
  const [selected, setSelected] = useState<LearningsAdjudicator>("dedup");
  const [markdown, setMarkdown] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!config) return;
    let cancelled = false;
    listLearnings(config)
      .then((r) => !cancelled && setPresent(r.present))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [config]);

  useEffect(() => {
    if (!config) return;
    let cancelled = false;
    setError(null);
    getLearnings(config, selected)
      .then((r) => {
        if (cancelled) return;
        setMarkdown(r.markdown);
        setDraft(r.markdown);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [config, selected]);

  const dirty = draft !== markdown;

  const save = useCallback(async () => {
    if (!config || !dirty) return;
    setSaving(true);
    setError(null);
    try {
      const r = await putLearnings(config, selected, draft);
      setMarkdown(r.markdown);
      setDraft(r.markdown);
      setPresent((prev) => (prev.includes(selected) ? prev : [...prev, selected]));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [config, dirty, draft, selected]);

  if (!config) return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;

  return (
    <div className="grid h-full min-h-0 grid-cols-[240px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col gap-1 border-r border-line-soft p-3">
        <div className="px-1 pb-2">
          <div className="text-sm font-semibold tracking-[-0.01em] text-ink">Learnings</div>
          <div className="text-2xs text-faint">corrections the assistant honors</div>
        </div>
        {ADJUDICATORS.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setSelected(a.id)}
            className={[
              "rounded-lg px-3 py-2 text-left transition-colors",
              selected === a.id
                ? "bg-surface-soft text-ink shadow-[inset_0_0_0_1px_var(--color-line-soft)]"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            ].join(" ")}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              {a.label}
              {present.includes(a.id) && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-label="has entries" />}
            </div>
            <div className="text-2xs text-faint">{a.hint}</div>
          </button>
        ))}
      </aside>

      <section className="flex min-h-0 flex-col gap-3 p-4">
        {error && <ListError title="Learnings error" message={error} />}
        <div className="flex items-center justify-between">
          <div className="text-2xs text-faint">
            Plain markdown. Edits save to <span className="font-mono">~/.ntrp/memory/learnings/{selected}.md</span>
          </div>
          <button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            className={[
              "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
              dirty && !saving
                ? "bg-accent text-on-accent hover:opacity-90"
                : "cursor-default bg-surface-soft text-faint",
            ].join(" ")}
          >
            {saving ? "Saving…" : dirty ? "Save" : "Saved"}
          </button>
        </div>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          placeholder={PLACEHOLDER}
          className="min-h-0 flex-1 resize-none rounded-xl border border-line-soft bg-surface p-4 font-mono text-sm leading-relaxed text-ink outline-none placeholder:text-faint focus:border-line"
        />
      </section>
    </div>
  );
}
