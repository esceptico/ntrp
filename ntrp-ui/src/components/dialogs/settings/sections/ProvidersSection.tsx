import { useEffect, useState } from "react";
import { colors } from "../../../ui/index.js";
import { getProviders, type ProviderInfo } from "../../../../api/client.js";
import type { Config } from "../../../../types.js";

interface ProvidersSectionProps {
  config: Config;
  selectedIndex: number;
  accent: string;
}

export function ProvidersSection({ config, selectedIndex, accent }: ProvidersSectionProps) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    getProviders(config).then(r => setProviders(r.providers)).catch(() => {});
  }, [config]);

  if (providers.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>  Loading...</span></text>
      </box>
    );
  }

  return (
    <box flexDirection="column">
      {providers.map((p, i) => {
        const selected = i === selectedIndex;
        const isCustom = p.id === "custom";

        return (
          <box key={p.id} flexDirection="row">
            <text>
              <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
              <span fg={selected ? colors.text.primary : colors.text.secondary}>{p.name.padEnd(28)}</span>
            </text>
            {isCustom ? (
              <text>
                <span fg={p.connected ? colors.status.success : colors.text.disabled}>
                  {p.model_count ? `${p.model_count} model${p.model_count !== 1 ? "s" : ""}` : "none"}
                </span>
              </text>
            ) : (
              <text>
                {p.connected ? (
                  <>
                    <span fg={colors.status.success}>{"\u2713 "}</span>
                    <span fg={colors.text.disabled}>{p.key_hint ?? ""}</span>
                    {p.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
                  </>
                ) : (
                  <span fg={colors.text.disabled}>not connected</span>
                )}
              </text>
            )}
          </box>
        );
      })}

      <box marginTop={1}>
        <text><span fg={colors.text.disabled}>  Use /connect to manage providers</span></text>
      </box>
    </box>
  );
}
