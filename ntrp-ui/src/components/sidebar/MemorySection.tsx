import React from "react";
import type { SidebarData } from "../../hooks/useSidebar.js";
import { SectionHeader, D, S } from "./shared.js";

export function MemorySection({ stats }: { stats: NonNullable<SidebarData["stats"]> }) {
  return (
    <box flexDirection="column">
      <SectionHeader label="MEMORY" />
      <text>
        <span fg={S}>{stats.fact_count}</span>
        <span fg={D}> facts</span>
      </text>
      <text>
        <span fg={S}>{stats.observation_count}</span>
        <span fg={D}> observations</span>
      </text>
    </box>
  );
}
