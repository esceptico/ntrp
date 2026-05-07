import { useState } from "react";
import clsx from "clsx";
import { NumberField } from "./Field";
import { updateServerConfig, fetchServerConfig } from "../../actions";
import type { ServerConfig } from "../../api";
import { useStore } from "../../store";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";

export function AgentTab({ serverConfig }: { serverConfig: ServerConfig | null }) {
  const connected = useStore((s) => s.connected);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  if (!serverConfig) {
    if (!connected) return <SettingsConnectionHint />;
    return <div className="text-[12.5px] text-faint">Loading agent settings…</div>;
  }

  const apply = async <K extends string>(key: K, value: unknown) => {
    setSavingKey(key);
    setError(null);
    try {
      await updateServerConfig({ [key]: value } as Parameters<typeof updateServerConfig>[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await fetchServerConfig();
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="grid gap-5">
      <div className="grid gap-0.5">
        <div className="text-[13px] font-medium text-ink">Reasoning</div>
        <div className="text-[11.5px] text-faint leading-[1.4]">
          How hard the model thinks before answering. Only some models support this; values are
          {" "}
          <span className="font-mono">
            {serverConfig.reasoning_efforts.length > 0
              ? serverConfig.reasoning_efforts.join(" / ")
              : "not available for this model"}
          </span>.
        </div>
        {serverConfig.reasoning_efforts.length > 0 && (
          <div className="flex gap-1.5 mt-2">
            {serverConfig.reasoning_efforts.map((effort) => {
              const active = serverConfig.reasoning_effort === effort;
              return (
                <button
                  key={effort}
                  type="button"
                  disabled={savingKey === "reasoning_effort"}
                  onClick={() => void apply("reasoning_effort", active ? null : effort)}
                  className={clsx(
                    "h-8 px-3 rounded-md text-[12px] font-medium tracking-[-0.005em] border transition-colors",
                    active
                      ? "bg-accent-soft border-accent/40 text-accent-strong"
                      : "bg-surface border-line text-ink-soft hover:border-line-strong",
                  )}
                >
                  {effort}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <NumberField
        label="Max sub-agent depth"
        help="How deep ntrp will spawn sub-agents before refusing to recurse further."
        value={serverConfig.max_depth}
        min={1}
        max={16}
        onChange={(n) => void apply("max_depth", n)}
      />

      {error && (
        <SettingsInlineError title="Couldn't save" message={error} />
      )}
    </div>
  );
}
