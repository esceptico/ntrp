import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { ServerConfig } from "../../api/client.js";
import { updateConfig, getServerConfig } from "../../api/client.js";
import type { Settings } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { MEMORY_NUMBER_ITEMS } from "../../components/dialogs/settings/config.js";

export interface UseMemorySettingsResult {
  memoryIndex: number;
  actionInProgress: string | null;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useMemorySettings(
  config: Config,
  serverConfig: ServerConfig | null,
  onServerConfigChange: (config: ServerConfig) => void,
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseMemorySettingsResult {
  const [memoryIndex, setMemoryIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const memoryEnabled = serverConfig?.sources?.memory?.enabled ?? false;
  const itemCount = memoryEnabled ? 3 : 1; // memory toggle, dreams toggle, consolidation

  const handleToggle = useCallback(async (source: string) => {
    if (actionInProgress || !serverConfig?.sources) return;
    const current = source === "dreams"
      ? serverConfig.sources.memory?.dreams ?? false
      : serverConfig.sources[source]?.enabled ?? false;
    setActionInProgress("Updating...");
    try {
      await updateConfig(config, { sources: { [source]: !current } });
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, serverConfig, actionInProgress, onServerConfigChange]);

  const handleKeypress = useCallback((key: Key) => {
    if (key.name === "up" || key.name === "k") {
      if (memoryIndex > 0) setMemoryIndex(i => i - 1);
    } else if (key.name === "down" || key.name === "j") {
      if (memoryIndex < itemCount - 1) setMemoryIndex(i => i + 1);
    } else if (key.name === "return" || key.name === "space") {
      if (memoryIndex === 0) handleToggle("memory");
      else if (memoryIndex === 1) handleToggle("dreams");
    } else if (key.name === "left" || key.name === "h") {
      if (memoryIndex === 2) {
        const item = MEMORY_NUMBER_ITEMS[0];
        const val = settings.agent[item.key as keyof typeof settings.agent] as number;
        const step = item.step ?? 1;
        if (val > item.min) onUpdate("agent", item.key, Math.max(item.min, val - step));
      }
    } else if (key.name === "right" || key.name === "l") {
      if (memoryIndex === 2) {
        const item = MEMORY_NUMBER_ITEMS[0];
        const val = settings.agent[item.key as keyof typeof settings.agent] as number;
        const step = item.step ?? 1;
        if (val < item.max) onUpdate("agent", item.key, Math.min(item.max, val + step));
      }
    }
  }, [memoryIndex, itemCount, handleToggle, settings, onUpdate]);

  return {
    memoryIndex,
    actionInProgress,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
