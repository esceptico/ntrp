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
      {(["chat", "res", "mem", "emb"] as const).map((label) => {
        const key = { chat: "chat_model", res: "research_model", mem: "memory_model", emb: "embedding_model" }[label] as keyof typeof cfg;
        const raw = (cfg[key] as string) ?? "";
        const display = formatModel(raw);
        return (
          <text key={label}>
            <span fg={D}>{label.padEnd(5)}</span>
            <span fg={S}>{truncateText(display, width - 5)}</span>
          </text>
        );
      })}
    </box>
  );
}
