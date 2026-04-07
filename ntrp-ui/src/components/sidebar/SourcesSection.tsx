import React from "react";
import { colors } from "../ui/colors.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D } from "./shared.js";

interface SourceEntry { key: string; label: string; on: boolean; error?: boolean }

function getSourceEntries(cfg: ServerConfig): SourceEntry[] {
  const sources = cfg.sources ?? {};
  const entries: SourceEntry[] = [];
  for (const [id, source] of Object.entries(sources)) {
    if (!source || typeof source !== "object") continue;
    const s = source as unknown as Record<string, unknown>;
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

export function SourcesSection({ cfg }: { cfg: ServerConfig }) {
  const entries = getSourceEntries(cfg);
  return (
    <box flexDirection="column">
      <SectionHeader label="SOURCES" />
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
