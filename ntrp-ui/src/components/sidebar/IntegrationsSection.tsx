import React from "react";
import { colors } from "../ui/colors.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D } from "./shared.js";

interface IntegrationEntry { key: string; label: string; on: boolean; error?: boolean }

function getIntegrationEntries(cfg: ServerConfig): IntegrationEntry[] {
  const integrations = cfg.integrations ?? {};
  const entries: IntegrationEntry[] = [];
  for (const [id, integration] of Object.entries(integrations)) {
    if (!integration || typeof integration !== "object") continue;
    const s = integration as unknown as Record<string, unknown>;
    const connected = id === "memory" || id === "google" ? !!s.enabled && !!s.connected : !!s.connected;
    entries.push({
      key: id,
      label: id,
      on: connected,
      error: !!s.error,
    });
  }
  return entries;
}

export function IntegrationsSection({ cfg }: { cfg: ServerConfig }) {
  const entries = getIntegrationEntries(cfg);
  return (
    <box flexDirection="column">
      <SectionHeader label="INTEGRATIONS" />
      {entries.map(({ key, label, on, error }) => {
        const color = error ? colors.status.error : on ? colors.status.success : D();
        return (
          <text key={key}>
            <span fg={color}>{error ? "!" : on ? "\u2022" : "\u00B7"}</span>
            <span fg={color}> {label}</span>
          </text>
        );
      })}
    </box>
  );
}
