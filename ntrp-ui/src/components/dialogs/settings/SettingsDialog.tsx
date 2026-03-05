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
  const [limitsIndex, setLimitsIndex] = useState(0);

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
    limitsIndex,
    setLimitsIndex,
    settings,
    serverConfig,
    onUpdate,
    onClose,
  });

  const browserOptions: SelectOption<string | null>[] = [
    { value: "chrome", title: "Chrome", indicator: serverConfig?.browser === "chrome" ? "●" : undefined },
    { value: "safari", title: "Safari", indicator: serverConfig?.browser === "safari" ? "●" : undefined },
    { value: "arc", title: "Arc", indicator: serverConfig?.browser === "arc" ? "●" : undefined },
    { value: null, title: "None (disable)", indicator: serverConfig?.browser == null ? "●" : undefined },
  ];

  if (state.showingBrowserDropdown) {
    return (
      <DialogSelect<string | null>
        title="Browser"
        options={browserOptions}
        initialIndex={Math.max(0, browserOptions.findIndex(o => o.value === (serverConfig?.browser || null)))}
        onSelect={(opt) => state.handleSelectBrowser(opt.value)}
        onClose={() => state.setShowingBrowserDropdown(false)}
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
                {activeSection === "providers" && (
                  <ProvidersSection
                    providers={state.providers}
                    selectedIndex={state.providersIndex}
                    accent={accent}
                    editing={state.editingProvider}
                    keyValue={state.providerKeyValue}
                    keyCursor={state.providerKeyCursor}
                    saving={state.providerSaving}
                    error={state.providerError}
                    confirmingDisconnect={state.providerConfirmDisconnect}
                  />
                )}

                {activeSection === "services" && (
                  <ServicesSection
                    services={state.services}
                    selectedIndex={state.servicesIndex}
                    accent={accent}
                    editing={state.editingService}
                    keyValue={state.serviceKeyValue}
                    keyCursor={state.serviceKeyCursor}
                    saving={state.serviceSaving}
                    error={state.serviceError}
                    confirmingDisconnect={state.serviceConfirmDisconnect}
                  />
                )}

                {activeSection === "server" && (
                  <ServerSection
                    serverUrl={state.serverUrl}
                    serverUrlCursor={state.serverUrlCursor}
                    apiKey={state.serverApiKey}
                    apiKeyCursor={state.serverApiKeyCursor}
                    selectedIndex={state.serverIndex}
                    editing={state.editingServer}
                    accent={accent}
                    saving={state.serverSaving}
                    error={state.serverError}
                  />
                )}

                {activeSection === "directives" && (
                  <DirectivesSection
                    content={state.directivesContent}
                    cursorPos={state.directivesCursorPos}
                    editing={state.editingDirectives}
                    saving={state.savingDirectives}
                    accent={accent}
                    height={contentHeight}
                  />
                )}

                {activeSection === "skills" && (
                  <SkillsSection skills={state.skills} accent={accent} width={detailWidth} />
                )}

                {activeSection === "connections" && (
                  <ConnectionsSection
                    serverConfig={serverConfig}
                    googleAccounts={state.googleAccounts}
                    selectedItem={state.connectionItem}
                    selectedGoogleIndex={state.selectedGoogleIndex}
                    accent={accent}
                    width={detailWidth}
                    editingVault={state.editingVault}
                    vaultPath={state.vaultPath}
                    vaultCursorPos={state.vaultCursorPos}
                    updatingVault={state.updatingVault}
                    vaultError={state.vaultError}
                    updatingBrowser={state.updatingBrowser}
                    browserError={state.browserError}
                  />
                )}

                {activeSection === "notifiers" && (
                  <NotifiersSection notifiers={state.notifiers} accent={accent} />
                )}

                {activeSection === "mcp" && (
                  <MCPSection
                    servers={state.mcp.mcpServers}
                    selectedIndex={state.mcp.mcpIndex}
                    accent={accent}
                    adding={state.mcp.mcpAdding}
                    addField={state.mcp.mcpAddField}
                    name={state.mcp.mcpName}
                    nameCursor={state.mcp.mcpNameCursor}
                    transport={state.mcp.mcpTransport}
                    command={state.mcp.mcpCommand}
                    commandCursor={state.mcp.mcpCommandCursor}
                    url={state.mcp.mcpUrl}
                    urlCursor={state.mcp.mcpUrlCursor}
                    saving={state.mcp.mcpSaving}
                    error={state.mcp.mcpError}
                    confirmingRemove={state.mcp.mcpConfirmRemove}
                  />
                )}

                {activeSection === "limits" && (
                  <LimitsSection
                    settings={settings.agent}
                    selectedIndex={limitsIndex}
                    accent={accent}
                  />
                )}
              </box>
            </box>

            {state.actionInProgress && (
              <box marginTop={1}>
                <text><span fg={colors.status.warning}>{state.actionInProgress}</span></text>
              </box>
            )}
          </>
        );
      }}
    </Dialog>
  );
}
