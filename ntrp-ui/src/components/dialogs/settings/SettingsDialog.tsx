import { useState } from "react";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { Dialog, colors, Hints } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import type { ServerConfig } from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS } from "./config.js";
import { DialogSelect, type SelectOption } from "../../ui/index.js";
import { ConnectionsSection } from "./ConnectionsSection.js";
import { DirectivesSection, LimitsSection, MCPSection, NotifiersSection, ProvidersSection, ServerSection, ServicesSection, SkillsSection } from "./sections/index.js";
import { useSettingsState } from "../../../hooks/useSettingsState.js";
import { useSettingsKeypress } from "../../../hooks/useSettingsKeypress.js";

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

  const [activeSection, setActiveSection] = useState<SectionId>("server");
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

  const browserOptions: SelectOption<string | null>[] = [
    { value: "chrome", title: "Chrome", indicator: serverConfig?.browser === "chrome" ? "●" : undefined },
    { value: "safari", title: "Safari", indicator: serverConfig?.browser === "safari" ? "●" : undefined },
    { value: "arc", title: "Arc", indicator: serverConfig?.browser === "arc" ? "●" : undefined },
    { value: null, title: "None (disable)", indicator: serverConfig?.browser == null ? "●" : undefined },
  ];

  if (state.connections.showingBrowserDropdown) {
    return (
      <DialogSelect<string | null>
        title="Browser"
        options={browserOptions}
        initialIndex={Math.max(0, browserOptions.findIndex(o => o.value === (serverConfig?.browser || null)))}
        onSelect={(opt) => state.connections.handleSelectBrowser(opt.value)}
        onClose={() => state.connections.setShowingBrowserDropdown(false)}
      />
    );
  }

  const footerHints = drilled
    ? [["↑↓", "navigate"], ["enter", "select"], ["←→", "adjust"], ["esc", "back"]] as [string, string][]
    : [["↑↓", "section"], ["enter", "open"], ["esc", "close"]] as [string, string][];

  return (
    <Dialog
      title="PREFERENCES"
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
                {activeSection === "providers" && <ProvidersSection providers={state.providers} accent={accent} />}
                {activeSection === "services" && <ServicesSection services={state.services} accent={accent} />}
                {activeSection === "server" && <ServerSection server={state.server} accent={accent} />}
                {activeSection === "directives" && <DirectivesSection directives={state.directives} accent={accent} height={contentHeight} />}
                {activeSection === "skills" && <SkillsSection skills={state.skills} accent={accent} width={detailWidth} />}
                {activeSection === "connections" && <ConnectionsSection connections={state.connections} serverConfig={serverConfig} accent={accent} width={detailWidth} />}
                {activeSection === "notifiers" && <NotifiersSection notifiers={state.notifiers} accent={accent} />}
                {activeSection === "mcp" && <MCPSection mcp={state.mcp} accent={accent} />}
                {activeSection === "limits" && <LimitsSection settings={settings.agent} selectedIndex={state.limits.limitsIndex} accent={accent} />}
              </box>
            </box>

            {state.connections.actionInProgress && (
              <box marginTop={1}>
                <text><span fg={colors.status.warning}>{state.connections.actionInProgress}</span></text>
              </box>
            )}
          </>
        );
      }}
    </Dialog>
  );
}
