import React from "react";
import type { Stats } from "../../api/memory.js";
import { SectionHeader, D, S } from "./shared.js";

export function MemorySection({ stats }: { stats: Stats }) {
  return (
    <box flexDirection="column">
      <SectionHeader label="MEMORY" />
      <text>
        <span fg={S()}>{stats.fact_count}</span>
        <span fg={D()}> facts</span>
      </text>
      <text>
        <span fg={S()}>{stats.observation_count}</span>
        <span fg={D()}> observations</span>
      </text>
      <text>
        <span fg={S()}>{stats.dream_count}</span>
        <span fg={D()}> dreams</span>
      </text>
    </box>
  );
}
