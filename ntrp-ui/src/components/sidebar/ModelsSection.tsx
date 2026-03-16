import React from "react";
import { truncateText } from "../../lib/utils.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D, S } from "./shared.js";

function formatModel(model?: string | null): string {
  if (!model) return "—";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

export function ModelsSection({ cfg, width }: { cfg: ServerConfig; width: number }) {
  return (
    <box flexDirection="column">
      <SectionHeader label="MODELS" />
      {(["chat", "rsrch", "mem", "emb"] as const).map((label) => {
        const key = { chat: "chat_model", rsrch: "research_model", mem: "memory_model", emb: "embedding_model" }[label] as keyof typeof cfg;
        const raw = (cfg[key] as string) ?? "";
        const isOAuth = raw.startsWith("oauth:");
        const display = formatModel(isOAuth ? raw.slice(6) : raw);
        return (
          <text key={label}>
            <span fg={D}>{label.padEnd(5)}</span>
            <span fg={S}>{truncateText(display, width - 5 - (isOAuth ? 4 : 0))}</span>
            {isOAuth && <span fg={D}> sub</span>}
          </text>
        );
      })}
    </box>
  );
}
