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
  reasoningEfforts: string[],
): UseAgentSettingsResult {
  const [agentIndex, setAgentIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    const total = AGENT_ITEMS.length + 1;
    const choices = [null, ...reasoningEfforts];
    if (handleListNav(key, total, setAgentIndex)) {
      // handled
    } else if ((key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") && agentIndex === 0) {
      if (reasoningEfforts.length === 0) return;
      const currentIdx = Math.max(0, choices.indexOf(settings.agent.reasoningEffort));
      const delta = key.name === "left" || key.name === "h" ? -1 : 1;
      const nextIdx = (currentIdx + delta + choices.length) % choices.length;
      onUpdate("agent", "reasoningEffort", choices[nextIdx]);
    } else if (key.name === "left" || key.name === "h") {
      const item = AGENT_ITEMS[agentIndex - 1];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val > item.min) onUpdate("agent", item.key, Math.max(item.min, val - step));
    } else if (key.name === "right" || key.name === "l") {
      const item = AGENT_ITEMS[agentIndex - 1];
      const val = settings.agent[item.key as keyof typeof settings.agent] as number;
      const step = item.step ?? 1;
      if (val < item.max) onUpdate("agent", item.key, Math.min(item.max, val + step));
    }
  }, [agentIndex, settings, onUpdate, reasoningEfforts]);

  return {
    agentIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
