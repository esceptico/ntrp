import { NumberRow, ToggleRow } from "../SettingsRows.js";
import { MEMORY_NUMBER_ITEMS } from "../config.js";
import type { ServerConfig } from "../../../../api/client.js";
import type { AgentSettings } from "../../../../hooks/useSettings.js";
import type { UseMemorySettingsResult } from "../../../../hooks/settings/useMemorySettings.js";

interface MemorySectionProps {
  memory: UseMemorySettingsResult;
  serverConfig: ServerConfig | null;
  agentSettings: AgentSettings;
  accent: string;
}

export function MemorySection({ memory, serverConfig, agentSettings, accent }: MemorySectionProps) {
  const sources = serverConfig?.integrations;
  const memoryEnabled = sources?.memory?.enabled ?? false;
  const dreamsEnabled = sources?.memory?.dreams ?? false;

  return (
    <box flexDirection="column">
      <ToggleRow
        id="item-0"
        header="Memory system"
        firstHeader
        label="Enabled"
        enabled={memoryEnabled}
        selected={memory.memoryIndex === 0}
        accent={accent}
      />

      {memoryEnabled && (
        <>
          <ToggleRow
            id="item-1"
            header="Dreams"
            label="Enabled"
            enabled={dreamsEnabled}
            selected={memory.memoryIndex === 1}
            accent={accent}
          />

          <NumberRow
            id="item-2"
            header="Consolidation"
            item={MEMORY_NUMBER_ITEMS[0]}
            value={agentSettings[MEMORY_NUMBER_ITEMS[0].key as keyof AgentSettings] as number}
            selected={memory.memoryIndex === 2}
            accent={accent}
            showDescription
          />
        </>
      )}
    </box>
  );
}
