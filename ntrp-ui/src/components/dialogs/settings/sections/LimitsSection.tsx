import { Box } from "ink";
import { NumberRow } from "../SettingsRows.js";
import { LIMIT_ITEMS } from "../config.js";
import type { AgentSettings } from "../../../../hooks/useSettings.js";

interface LimitsSectionProps {
  settings: AgentSettings;
  selectedIndex: number;
  accent: string;
}

export function LimitsSection({
  settings,
  selectedIndex,
  accent,
}: LimitsSectionProps) {
  return (
    <Box flexDirection="column">
      {LIMIT_ITEMS.map((item, idx) => (
        <NumberRow
          key={item.key}
          item={item}
          value={settings[item.key as keyof AgentSettings] as number}
          selected={idx === selectedIndex}
          accent={accent}
        />
      ))}
    </Box>
  );
}
