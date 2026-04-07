import React from "react";
import { colors } from "../ui/colors.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D, S } from "./shared.js";

interface SourceEntry { key: string; label: string; on: boolean; error?: boolean }

function getSourceEntries(cfg: ServerConfig): SourceEntry[] {
  const sources = cfg.sources;
  return [
    { key: "vault", label: "notes", on: !!cfg.has_notes },
    { key: "google", label: "google", on: !!sources?.google?.enabled && !!sources?.google?.connected, error: !!sources?.google?.error },
    { key: "memory", label: "memory", on: !!sources?.memory?.enabled },
    { key: "web", label: "web", on: !!sources?.web?.connected },
    { key: "slack", label: "slack", on: !!sources?.slack?.connected, error: !!sources?.slack?.error },
  ];
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
