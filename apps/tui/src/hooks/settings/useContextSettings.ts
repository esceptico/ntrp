import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { CONTEXT_ITEMS } from "../../components/dialogs/settings/config.js";
import { handleListNav } from "../keyUtils.js";

export interface UseContextSettingsResult {
  contextIndex: number;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useContextSettings(
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseContextSettingsResult {
  const [contextIndex, setContextIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    if (handleListNav(key, CONTEXT_ITEMS.length, setContextIndex)) {
      // handled
    } else if (key.name === "left" || key.name === "h") {
      const item = CONTEXT_ITEMS[contextIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val > item.min) onUpdate("agent", item.key, Math.max(item.min, val - step));
    } else if (key.name === "right" || key.name === "l") {
      const item = CONTEXT_ITEMS[contextIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val < item.max) onUpdate("agent", item.key, Math.min(item.max, val + step));
    }
  }, [contextIndex, settings, onUpdate]);

  return {
    contextIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
