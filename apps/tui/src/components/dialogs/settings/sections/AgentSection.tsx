import { CycleRow, NumberRow } from "../SettingsRows.js";
import { AGENT_ITEMS } from "../config.js";
import type { AgentSettings } from "../../../../hooks/useSettings.js";
import { colors } from "../../../ui/colors.js";

interface AgentSectionProps {
  settings: AgentSettings;
  reasoningEfforts: string[];
  selectedIndex: number;
  accent: string;
}

function reasoningLabel(settings: AgentSettings, efforts: string[]): string {
  if (efforts.length === 0) return "not supported";
  if (settings.reasoningEffort === null) return "default";
  return efforts.includes(settings.reasoningEffort) ? settings.reasoningEffort : "default";
}

export function AgentSection({ settings, reasoningEfforts, selectedIndex, accent }: AgentSectionProps) {
  const depthItem = AGENT_ITEMS[0];
  return (
    <box flexDirection="column">
      <CycleRow
        label="Reasoning"
        value={reasoningLabel(settings, reasoningEfforts)}
        selected={selectedIndex === 0}
        accent={accent}
        valueColor={reasoningEfforts.length === 0 ? colors.text.disabled : undefined}
      />
      {reasoningEfforts.length === 0 && (
        <box marginLeft={20}>
          <text><span fg={colors.text.disabled}>Current chat model has no reasoning-effort variants</span></text>
        </box>
      )}
      <NumberRow
        item={depthItem}
        value={settings.maxDepth}
        valueWidth={String(depthItem.max).length}
        selected={selectedIndex === 1}
        accent={accent}
        showDescription
      />
    </box>
  );
}
