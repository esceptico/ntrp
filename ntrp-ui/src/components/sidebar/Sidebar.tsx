import React from "react";
import { truncateText } from "../../lib/utils.js";
import { useAccentColor, type SessionNotification } from "../../hooks/index.js";
import type { ServerConfig } from "../../api/client.js";
import type { Config } from "../../types.js";
import type { SidebarData } from "../../hooks/useSidebar.js";
import type { SidebarSettings } from "../../hooks/useSettings.js";
import { D, type UsageData } from "./shared.js";
import { ModelsSection } from "./ModelsSection.js";
import { ContextSection } from "./ContextSection.js";
import { UsageSection } from "./UsageSection.js";
import { IntegrationsSection } from "./IntegrationsSection.js";
import { AutomationsSection } from "./AutomationsSection.js";
import { SessionsList } from "./SessionsList.js";
import { MemorySection } from "./MemorySection.js";

interface SidebarProps {
  config: Config;
  serverConfig: ServerConfig | null;
  serverVersion: string | null;
  data: SidebarData;
  usage: UsageData;
  width: number;
  height: number;
  currentSessionId: string | null;
  sessionStates?: Map<string, SessionNotification>;
  sections: SidebarSettings;
  onSessionClick?: (sessionId: string) => void;
}

export const Sidebar = React.memo(function Sidebar({ config, serverConfig, serverVersion, data, usage, width, height, currentSessionId, sessionStates, sections, onSessionClick }: SidebarProps) {
  const { accentValue } = useAccentColor();
  const contentWidth = width - 2;

  return (
    <scrollbox
      width={width}
      height={height}
      style={{ scrollbarOptions: { visible: false } }}
    >
      <box flexDirection="column" paddingX={1} paddingTop={1} gap={1}>
        <box flexDirection="column">
          <text>
            <span fg={accentValue}>ntrp</span>
            {serverVersion && <span fg={D()}> v{serverVersion}</span>}
          </text>
          <text><span fg={D()}>{truncateText(config.serverUrl, contentWidth)}</span></text>
        </box>

        {sections.models && serverConfig && <ModelsSection cfg={serverConfig} width={contentWidth} />}
        {sections.context && data.context && <ContextSection context={data.context} width={contentWidth} />}
        {sections.usage && <UsageSection usage={usage} />}
        {sections.integrations && serverConfig && <IntegrationsSection cfg={serverConfig} />}
        {sections.automations && data.nextAutomations.length > 0 && <AutomationsSection automations={data.nextAutomations} width={contentWidth} config={config} />}
        {sections.memory_stats && data.memoryStats && <MemorySection stats={data.memoryStats} />}

        {sections.sessions && data.sessions.length > 0 && (
          <SessionsList
            sessions={data.sessions}
            currentSessionId={currentSessionId}
            sessionStates={sessionStates}
            width={contentWidth}
            onSessionClick={onSessionClick}
          />
        )}
      </box>
    </scrollbox>
  );
});
