import { useState } from "react";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { Dialog, colors, Hints } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { ServerConfig } from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS } from "./config.js";
import {
  ConnectionSection, ApiKeysSection, IntegrationsSection, MemorySection,
  DirectivesSection, ContextSection, AgentSection,
  NotifiersSection, SkillsSection, MCPSection, InterfaceSection,
} from "./sections/index.js";
import { useSettingsState } from "../../../hooks/useSettingsState.js";
import { useSettingsKeypress } from "../../../hooks/useSettingsKeypress.js";
import { getSectionHints } from "./sectionHints.js";
import { reasoningEfforts } from "../../../lib/reasoning.js";

interface SettingsDialogProps {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onRefreshIndexStatus: () => Promise<void>;
  onClose: () => void;
  onServerCredentialsChange: (config: Config) => void;
}

export function SettingsDialog({
  config,
  serverConfig,
  settings,
  onUpdate,
  onServerConfigChange,
  onRefreshIndexStatus,
  onClose,
  onServerCredentialsChange,
}: SettingsDialogProps) {
  const { accentValue: accent } = useAccentColor();

  const [activeSection, setActiveSection] = useState<SectionId>("connection");
  const [drilled, setDrilled] = useState(false);

  const state = useSettingsState({
    config,
    serverConfig,
    settings,
    onUpdate,
    onServerConfigChange,
    onServerCredentialsChange,
  });

  useSettingsKeypress({
    state,
    activeSection,
    drilled,
    setDrilled,
    setActiveSection,
    onClose,
  });

  const footerHints = !drilled
    ? [["↑↓", "section"], ["enter", "open"], ["esc", "close"]] as [string, string][]
    : getSectionHints(activeSection, state, serverConfig);

  return (
    <Dialog
      title="SYSTEM CONFIG"
      size="large"
      onClose={onClose}
      footer={<Hints items={footerHints} />}
    >
      {({ width, height }) => {
        const sidebarWidth = 16;
        const detailWidth = Math.max(0, width - sidebarWidth - 3);
        const contentHeight = Math.max(1, height - 1);

        return (
          <>
            <box flexDirection="row">
              {/* Sidebar */}
              <box flexDirection="column" width={sidebarWidth}>
                {SECTION_IDS.map((section) => {
                  const isActive = section === activeSection;
                  return (
                    <text key={section}>
                      <span fg={isActive ? accent : colors.text.disabled}>{isActive ? "▸ " : "  "}</span>
                      {isActive ? (
                        <span fg={accent}><strong>{SECTION_LABELS[section]}</strong></span>
                      ) : (
                        <span fg={colors.text.secondary}>{SECTION_LABELS[section]}</span>
                      )}
                    </text>
                  );
                })}
              </box>

              {/* Divider */}
              <box flexDirection="column" width={1} marginX={1}>
                {Array.from({ length: contentHeight }).map((_, i) => (
                  <text key={i}><span fg={colors.divider}>│</span></text>
                ))}
              </box>

              {/* Detail pane */}
              <box flexDirection="column" width={detailWidth} height={contentHeight} overflow="hidden">
                {activeSection === "connection" && <ConnectionSection server={state.server} accent={accent} />}
                {activeSection === "apiKeys" && <ApiKeysSection providers={state.providers} accent={accent} />}
                {activeSection === "integrations" && <IntegrationsSection connections={state.connections} services={state.services} activeList={state.integrationsNav.activeList} serverConfig={serverConfig} accent={accent} width={detailWidth} />}
                {activeSection === "memory" && <MemorySection memory={state.memory} serverConfig={serverConfig} agentSettings={settings.agent} accent={accent} />}
                {activeSection === "instructions" && <DirectivesSection directives={state.directives} accent={accent} height={contentHeight} />}
                {activeSection === "context" && <ContextSection settings={settings.agent} selectedIndex={state.context.contextIndex} accent={accent} />}
                {activeSection === "agent" && <AgentSection settings={settings.agent} reasoningEfforts={reasoningEfforts(serverConfig)} selectedIndex={state.agent.agentIndex} accent={accent} />}
                {activeSection === "notifications" && <NotifiersSection notifiers={state.notifiers} accent={accent} />}
                {activeSection === "skills" && <SkillsSection skills={state.skills} accent={accent} width={detailWidth} height={contentHeight} />}
                {activeSection === "mcp" && <MCPSection mcp={state.mcp} accent={accent} width={detailWidth} height={contentHeight} />}
                {activeSection === "interface" && <InterfaceSection ui={settings.ui} sidebar={settings.sidebar} selectedIndex={state.iface.interfaceIndex} accent={accent} height={contentHeight} />}
              </box>
            </box>

            {(state.connections.actionInProgress || state.memory.actionInProgress) && (
              <box marginTop={1}>
                <text><span fg={colors.status.warning}>{state.connections.actionInProgress || state.memory.actionInProgress}</span></text>
              </box>
            )}
          </>
        );
      }}
    </Dialog>
  );
}
