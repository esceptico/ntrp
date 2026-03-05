import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { LIMIT_ITEMS } from "../../components/dialogs/settings/config.js";
import { handleListNav } from "../keyUtils.js";

export interface UseLimitsResult {
  limitsIndex: number;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useLimits(
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseLimitsResult {
  const [limitsIndex, setLimitsIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    if (handleListNav(key, LIMIT_ITEMS.length, setLimitsIndex)) {
      // handled
    } else if (key.name === "left" || key.name === "h") {
      const item = LIMIT_ITEMS[limitsIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      if (val > item.min) onUpdate("agent", item.key, val - 1);
    } else if (key.name === "right" || key.name === "l") {
      const item = LIMIT_ITEMS[limitsIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      if (val < item.max) onUpdate("agent", item.key, val + 1);
    }
  }, [limitsIndex, settings, onUpdate]);

  return {
    limitsIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
