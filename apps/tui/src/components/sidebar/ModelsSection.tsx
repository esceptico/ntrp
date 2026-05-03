import React from "react";
import { truncateText } from "../../lib/utils.js";
import type { ServerConfig } from "../../api/client.js";
import { SectionHeader, D, S } from "./shared.js";
import { currentReasoningEffort } from "../../lib/reasoning.js";

const LABEL_WIDTH = 6;

function formatModel(model?: string | null): string {
  if (!model) return "—";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

export function ModelsSection({ cfg, width }: { cfg: ServerConfig; width: number }) {
  const reasoning = currentReasoningEffort(cfg);
  return (
    <box flexDirection="column">
      <SectionHeader label="MODELS" />
      {(["chat", "res", "mem", "emb"] as const).map((label) => {
        const key = { chat: "chat_model", res: "research_model", mem: "memory_model", emb: "embedding_model" }[label] as keyof typeof cfg;
        const raw = (cfg[key] as string) ?? "";
        const display = formatModel(raw);
        return (
          <text key={label}>
            <span fg={D()}>{label.padEnd(LABEL_WIDTH)}</span>
            <span fg={S()}>{truncateText(display, width - LABEL_WIDTH)}</span>
          </text>
        );
      })}
      {reasoning && (
        <text>
          <span fg={D()}>{"think".padEnd(LABEL_WIDTH)}</span>
          <span fg={S()}>{reasoning}</span>
        </text>
      )}
    </box>
  );
}
