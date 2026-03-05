import React from "react";
import { colors } from "../ui/colors.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D, S } from "./shared.js";

interface SourceEntry { key: string; label: string; on: boolean; error?: boolean }

function getSourceEntries(cfg: ServerConfig): SourceEntry[] {
  const sources = cfg.sources;
  return [
    { key: "vault", label: "notes", on: !!cfg.has_notes },
    { key: "gmail", label: "gmail", on: !!sources?.gmail?.enabled && !!sources?.gmail?.connected, error: !!sources?.gmail?.error },
    { key: "calendar", label: "cal", on: !!sources?.calendar?.enabled && !!sources?.calendar?.connected, error: !!sources?.calendar?.error },
    { key: "browser", label: "browser", on: !!cfg.has_browser },
    { key: "memory", label: "memory", on: !!sources?.memory?.enabled },
    { key: "web", label: "web", on: !!sources?.web?.connected },
  ];
}

export function SourcesSection({ cfg }: { cfg: ServerConfig }) {
  const entries = getSourceEntries(cfg);
  return (
    <box flexDirection="column">
      <SectionHeader label="SOURCES" />
      {entries.map(({ key, label, on, error }) => {
        const color = error ? colors.status.error : on ? S : D;
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
