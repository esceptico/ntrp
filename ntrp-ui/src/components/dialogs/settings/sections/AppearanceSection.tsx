import { Box } from "ink";
import { BooleanRow, ColorPicker } from "../SettingsRows.js";
import { APPEARANCE_ITEMS } from "../config.js";
import type { UiSettings } from "../../../../hooks/useSettings.js";

interface AppearanceSectionProps {
  settings: UiSettings;
  selectedIndex: number;
  accent: string;
}

export function AppearanceSection({
  settings,
  selectedIndex,
  accent,
}: AppearanceSectionProps) {
  const isColorItem = selectedIndex === APPEARANCE_ITEMS.length;

  return (
    <Box flexDirection="column">
      {APPEARANCE_ITEMS.map((item, index) => (
        <BooleanRow
          key={item.key}
          item={item}
          value={settings[item.key as keyof UiSettings] as boolean}
          selected={index === selectedIndex}
          accent={accent}
        />
      ))}
      <Box marginTop={1}>
        <ColorPicker
          currentColor={settings.accentColor}
          selected={isColorItem}
          accent={accent}
        />
      </Box>
    </Box>
  );
}
