import { useState } from "react";
import { NumberField } from "./Field";
import { updateServerConfig, fetchServerConfig } from "../../actions";
import type { ServerConfig } from "../../api";
import { useStore } from "../../store";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";

export function AgentTab({ serverConfig }: { serverConfig: ServerConfig | null }) {
  const connected = useStore((s) => s.connected);
  const [error, setError] = useState<string | null>(null);

  if (!serverConfig) {
    if (!connected) return <SettingsConnectionHint />;
    return <div className="text-sm text-muted">Loading agent settings…</div>;
  }

  const apply = async <K extends string>(key: K, value: unknown) => {
    setError(null);
    try {
      await updateServerConfig({ [key]: value } as Parameters<typeof updateServerConfig>[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await fetchServerConfig();
    }
  };

  return (
    <div className="grid gap-5">
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
