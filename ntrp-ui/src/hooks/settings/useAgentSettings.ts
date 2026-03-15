import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { AGENT_ITEMS } from "../../components/dialogs/settings/config.js";
import { handleListNav } from "../keyUtils.js";

export interface UseAgentSettingsResult {
  agentIndex: number;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useAgentSettings(
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseAgentSettingsResult {
  const [agentIndex, setAgentIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    if (handleListNav(key, AGENT_ITEMS.length, setAgentIndex)) {
      // handled
    } else if (key.name === "left" || key.name === "h") {
      const item = AGENT_ITEMS[agentIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val > item.min) onUpdate("agent", item.key, Math.max(item.min, val - step));
    } else if (key.name === "right" || key.name === "l") {
      const item = AGENT_ITEMS[agentIndex];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val < item.max) onUpdate("agent", item.key, Math.min(item.max, val + step));
    }
  }, [agentIndex, settings, onUpdate]);

  return {
    agentIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
