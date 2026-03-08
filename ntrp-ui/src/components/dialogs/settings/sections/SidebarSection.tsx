import { colors, SelectionIndicator } from "../../../ui/index.js";
import { SIDEBAR_SECTION_IDS, type SidebarSettings, type SidebarSectionId } from "../../../../hooks/useSettings.js";

const LABELS: Record<SidebarSectionId, string> = {
  models: "Models",
  context: "Context",
  usage: "Usage",
  sources: "Sources",
  automations: "Automations",
  sessions: "Sessions",
  memory_stats: "Memory",
};

interface SidebarSectionProps {
  sidebar: SidebarSettings;
  selectedIndex: number;
  accent: string;
}

export function SidebarSection({ sidebar, selectedIndex, accent }: SidebarSectionProps) {
  return (
    <box flexDirection="column">
      {SIDEBAR_SECTION_IDS.map((id, idx) => {
        const selected = idx === selectedIndex;
        const enabled = sidebar[id];
        return (
          <text key={id}>
            <SelectionIndicator selected={selected} accent={accent} />
            <span fg={enabled ? (selected ? accent : colors.text.primary) : colors.text.muted}>
              {enabled ? "\u25CF" : "\u25CB"}
            </span>
            <span fg={selected ? colors.text.primary : colors.text.secondary}> {LABELS[id]}</span>
          </text>
        );
      })}
    </box>
  );
}
