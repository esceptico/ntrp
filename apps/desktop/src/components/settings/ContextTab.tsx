import { useEffect, useState } from "react";
import { NumberField, PercentField } from "./Field";
import { updateServerConfig, fetchServerConfig } from "../../actions";
import type { ServerConfig, ServerConfigPatch } from "../../api";

type Draft = Pick<
  ServerConfig,
  | "compression_threshold"
  | "max_messages"
  | "compression_keep_ratio"
  | "summary_max_tokens"
  | "consolidation_interval"
>;

const KEYS: Array<keyof Draft> = [
  "compression_threshold",
  "max_messages",
  "compression_keep_ratio",
  "summary_max_tokens",
  "consolidation_interval",
];

export function ContextTab({ serverConfig }: { serverConfig: ServerConfig | null }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!serverConfig) return;
    setDraft({
      compression_threshold: serverConfig.compression_threshold,
      max_messages: serverConfig.max_messages,
      compression_keep_ratio: serverConfig.compression_keep_ratio,
      summary_max_tokens: serverConfig.summary_max_tokens,
      consolidation_interval: serverConfig.consolidation_interval,
    });
  }, [serverConfig]);

  if (!serverConfig || !draft) {
    return <div className="text-[12.5px] text-faint">Loading context settings…</div>;
  }

  const dirty = KEYS.some((k) => draft[k] !== serverConfig[k]);

  const update = (patch: Partial<Draft>) => setDraft((prev) => (prev ? { ...prev, ...patch } : prev));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dirty || saving) return;
    setSaving(true);
    setError(null);
    try {
      const patch: ServerConfigPatch = {};
      for (const k of KEYS) {
        if (draft[k] !== serverConfig[k]) {
          (patch as Record<string, unknown>)[k] = draft[k];
        }
      }
      await updateServerConfig(patch);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await fetchServerConfig();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid gap-5">
      <p className="text-[12.5px] text-muted leading-[1.45] max-w-[440px]">
        Controls when the agent compresses its conversation history and how aggressively old turns
        are summarised away.
      </p>

      <PercentField
        label="Compression threshold"
        help="Share of the model's context window used before older turns start being compressed."
        value={draft.compression_threshold}
        min={10}
        max={100}
        onChange={(n) => update({ compression_threshold: n })}
      />

      <NumberField
        label="Max messages"
        help="Hard cap on the number of raw messages kept before compression kicks in."
        value={draft.max_messages}
        min={10}
        max={1000}
        onChange={(n) => update({ max_messages: n })}
      />

      <PercentField
        label="Keep ratio"
        help="Share of recent messages preserved verbatim during compression."
        value={draft.compression_keep_ratio}
        min={0}
        max={100}
        onChange={(n) => update({ compression_keep_ratio: n })}
      />

      <NumberField
        label="Summary max tokens"
        suffix="tokens"
        help="Upper bound on each compression summary."
        value={draft.summary_max_tokens}
        min={256}
        max={8000}
        onChange={(n) => update({ summary_max_tokens: n })}
      />

      <NumberField
        label="Consolidation interval"
        suffix="messages"
        help="How many user messages between memory consolidation passes."
        value={draft.consolidation_interval}
        min={1}
        max={500}
        onChange={(n) => update({ consolidation_interval: n })}
      />

      {error && (
        <div className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
          <strong className="text-bad text-[12px] font-semibold">Couldn't save</strong>
          <span className="text-[12px] text-[#8a3220] leading-[1.4]">{error}</span>
        </div>
      )}

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={!dirty || saving}
          className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[9px] bg-ink text-on-ink text-[12.5px] font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>
    </form>
  );
}
