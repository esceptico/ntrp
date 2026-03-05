import React from "react";
import { truncateText } from "../../lib/utils.js";
import { useAccentColor, type SessionNotification } from "../../hooks/index.js";
import type { ServerConfig } from "../../api/client.js";
import type { SidebarData } from "../../hooks/useSidebar.js";
import { D, type UsageData } from "./shared.js";
import { ModelsSection } from "./ModelsSection.js";
import { ContextSection } from "./ContextSection.js";
import { UsageSection } from "./UsageSection.js";
import { MemorySection } from "./MemorySection.js";
import { SourcesSection } from "./SourcesSection.js";
import { AutomationsSection } from "./AutomationsSection.js";
import { SessionsList } from "./SessionsList.js";

interface SidebarProps {
  serverConfig: ServerConfig | null;
  serverVersion: string | null;
  serverUrl: string;
  data: SidebarData;
  usage: UsageData;
  width: number;
  height: number;
  currentSessionId: string | null;
  currentSessionName: string | null;
  sessionStates?: Map<string, SessionNotification>;
}

export const Sidebar = React.memo(function Sidebar({ serverConfig, serverVersion, serverUrl, data, usage, width, height, currentSessionId, currentSessionName, sessionStates }: SidebarProps) {
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
            {serverVersion && <span fg={D}> v{serverVersion}</span>}
          </text>
          <text><span fg={D}>{truncateText(serverUrl, contentWidth)}</span></text>
        </box>

        {serverConfig && <ModelsSection cfg={serverConfig} width={contentWidth} />}
        {data.context && <ContextSection context={data.context} width={contentWidth} />}
        {(usage.prompt > 0 || usage.completion > 0) && <UsageSection usage={usage} />}
        {data.stats && <MemorySection stats={data.stats} />}
        {serverConfig && <SourcesSection cfg={serverConfig} />}
        {data.nextAutomations.length > 0 && <AutomationsSection automations={data.nextAutomations} width={contentWidth} />}

        {data.sessions.length > 0 && (
          <SessionsList
            sessions={data.sessions}
            currentSessionId={currentSessionId}
            sessionStates={sessionStates}
            width={contentWidth}
          />
        )}
      </box>
    </scrollbox>
  );
});
