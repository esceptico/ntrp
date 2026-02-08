import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, colors, accentColors, type AccentColor } from "../../ui/index.js";
import {
  getSupportedModels,
  updateConfig,
  getGoogleAccounts,
  addGoogleAccount,
  removeGoogleAccount,
  getEmbeddingModels,
  updateEmbeddingModel,
  updateVaultPath,
  updateBrowser,
  getServerConfig,
  type ServerConfig,
  type GoogleAccount,
} from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS, APPEARANCE_ITEMS, LIMIT_ITEMS, CONNECTION_ITEMS, TOGGLEABLE_SOURCES, type ConnectionItem } from "./config.js";
import { colorOptions } from "./SettingsRows.js";
import { ModelDropdown } from "./ModelDropdown.js";
import { BrowserDropdown } from "./BrowserDropdown.js";
import { ConnectionsSection } from "./ConnectionsSection.js";
import { AgentSection, AppearanceSection, LimitsSection } from "./sections/index.js";
import { useTextInput } from "../../../hooks/useTextInput.js";

function useAccent(accentColor: AccentColor) {
  return useMemo(() => accentColors[accentColor].primary, [accentColor]);
}

type DropdownTarget = "chat" | "memory" | "embedding" | null;

interface SettingsDialogProps {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onModelChange: (type: "chat" | "memory", model: string) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onClose: () => void;
}

export function SettingsDialog({
  config,
  serverConfig,
  settings,
  onUpdate,
  onModelChange,
  onServerConfigChange,
  onClose,
}: SettingsDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const accent = useAccent(settings.ui.accentColor);

  const [activeSection, setActiveSection] = useState<SectionId>("agent");
  const [agentIndex, setAgentIndex] = useState(0);
  const [appearanceIndex, setAppearanceIndex] = useState(0);
  const [limitsIndex, setLimitsIndex] = useState(0);

  // Connections state
  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  // Vault editing state
  const [editingVault, setEditingVault] = useState(false);
  const [vaultPath, setVaultPath] = useState(serverConfig?.vault_path || "");
  const [vaultCursorPos, setVaultCursorPos] = useState(0);
  const [updatingVault, setUpdatingVault] = useState(false);
  const [vaultError, setVaultError] = useState<string | null>(null);

  // Browser editing state
  const [showingBrowserDropdown, setShowingBrowserDropdown] = useState(false);
  const [updatingBrowser, setUpdatingBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  // Models state
  const [models, setModels] = useState<string[]>([]);
  const [chatModel, setChatModel] = useState(serverConfig?.chat_model ?? "");
  const [memoryModel, setMemoryModel] = useState(serverConfig?.memory_model ?? "");
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [embeddingModel, setEmbeddingModel] = useState(serverConfig?.embedding_model ?? "");
  const [modelUpdating, setModelUpdating] = useState(false);
  const [dropdownTarget, setDropdownTarget] = useState<DropdownTarget>(null);
  const [pendingEmbeddingModel, setPendingEmbeddingModel] = useState<string | null>(null);

  const contentWidth = Math.max(0, terminalWidth - 4);
  const sidebarWidth = 16;
  const detailWidth = Math.max(0, contentWidth - sidebarWidth - 3);
  const modelNameWidth = Math.max(0, detailWidth - 20);

  // Fetch models
  useEffect(() => {
    getSupportedModels(config)
      .then((result) => {
        setModels(result.models);
        if (!chatModel) setChatModel(result.chat_model);
        if (!memoryModel) setMemoryModel(result.memory_model);
      })
      .catch(() => {});
    getEmbeddingModels(config)
      .then((result) => {
        setEmbeddingModels(result.models);
        if (!embeddingModel) setEmbeddingModel(result.current);
      })
      .catch(() => {});
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch google accounts
  useEffect(() => {
    getGoogleAccounts(config)
      .then((result) => setGoogleAccounts(result.accounts))
      .catch(() => {});
  }, [config]);

  const agentTotalItems = 3;
  const appearanceTotalItems = APPEARANCE_ITEMS.length + 1;
  const limitsTotalItems = LIMIT_ITEMS.length;
  const isColorItem = activeSection === "appearance" && appearanceIndex === APPEARANCE_ITEMS.length;

  const selectModel = useCallback(
    (modelType: "chat" | "memory", modelName: string) => {
      if (modelUpdating) return;
      if (modelType === "chat") {
        if (modelName === chatModel) return;
        setChatModel(modelName);
        onModelChange("chat", modelName);
        setModelUpdating(true);
        updateConfig(config, { chat_model: modelName })
          .catch(() => {})
          .finally(() => setModelUpdating(false));
      } else {
        if (modelName === memoryModel) return;
        setMemoryModel(modelName);
        onModelChange("memory", modelName);
        setModelUpdating(true);
        updateConfig(config, { memory_model: modelName })
          .catch(() => {})
          .finally(() => setModelUpdating(false));
      }
    },
    [config, chatModel, memoryModel, modelUpdating, onModelChange]
  );

  const handleAddGoogle = useCallback(async () => {
    if (actionInProgress) return;
    setActionInProgress("Adding account...");
    try {
      await addGoogleAccount(config);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
    } catch {
      // Ignore errors
    } finally {
      setActionInProgress(null);
    }
  }, [config, actionInProgress]);

  const handleRemoveGoogle = useCallback(async () => {
    if (actionInProgress || googleAccounts.length === 0) return;
    const account = googleAccounts[selectedGoogleIndex];
    if (!account) return;

    setActionInProgress("Removing...");
    try {
      await removeGoogleAccount(config, account.token_file);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
      setSelectedGoogleIndex(Math.max(0, selectedGoogleIndex - 1));
    } catch {
      // Ignore errors
    } finally {
      setActionInProgress(null);
    }
  }, [config, googleAccounts, selectedGoogleIndex, actionInProgress]);

  // Vault editing handlers
  const { handleKey: handleVaultKey } = useTextInput({
    text: vaultPath,
    cursorPos: vaultCursorPos,
    setText: setVaultPath,
    setCursorPos: setVaultCursorPos,
  });

  const handleSaveVault = useCallback(async () => {
    if (updatingVault) return;
    const trimmed = vaultPath.trim();
    if (!trimmed) {
      setVaultError("Path cannot be empty");
      return;
    }
    setVaultError(null);
    setUpdatingVault(true);
    try {
      await updateVaultPath(config, trimmed);
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
      setEditingVault(false);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Failed to update vault path");
    } finally {
      setUpdatingVault(false);
    }
  }, [config, vaultPath, updatingVault, onServerConfigChange]);

  const handleCancelVaultEdit = useCallback(() => {
    setVaultPath(serverConfig?.vault_path || "");
    setVaultCursorPos(0);
    setVaultError(null);
    setEditingVault(false);
  }, [serverConfig?.vault_path]);

  const handleStartVaultEdit = useCallback(() => {
    const path = serverConfig?.vault_path || "";
    setVaultPath(path);
    setVaultCursorPos(path.length);
    setVaultError(null);
    setEditingVault(true);
  }, [serverConfig?.vault_path]);

  // Browser selection handler
  const handleSelectBrowser = useCallback(async (browser: string | null) => {
    setShowingBrowserDropdown(false);
    if (browser === serverConfig?.browser) return;

    setBrowserError(null);
    setUpdatingBrowser(true);
    try {
      await updateBrowser(config, browser);
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch (err) {
      setBrowserError(err instanceof Error ? err.message : "Failed to update browser");
    } finally {
      setUpdatingBrowser(false);
    }
  }, [config, serverConfig?.browser, onServerConfigChange]);

  const handleToggleSource = useCallback(async (source: string) => {
    if (actionInProgress || !serverConfig?.sources) return;
    const current = serverConfig.sources[source]?.enabled ?? false;
    setActionInProgress("Updating...");
    try {
      await updateConfig(config, { sources: { [source]: !current } });
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch {
      // Ignore errors
    } finally {
      setActionInProgress(null);
    }
  }, [config, serverConfig, actionInProgress, onServerConfigChange]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (dropdownTarget || actionInProgress) return;

      if (key.name === "escape" || key.name === "q") {
        onClose();
        return;
      }

      if (key.name === "tab") {
        const direction = key.shift ? -1 : 1;
        const idx = SECTION_IDS.indexOf(activeSection);
        const next = (idx + direction + SECTION_IDS.length) % SECTION_IDS.length;
        setActiveSection(SECTION_IDS[next]);
        return;
      }

      if (activeSection === "agent") {
        if (key.name === "up" || key.name === "k") {
          setAgentIndex((i) => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setAgentIndex((i) => Math.min(agentTotalItems - 1, i + 1));
        } else if (key.name === "return" || key.name === "space") {
          if (agentIndex === 0) setDropdownTarget("chat");
          else if (agentIndex === 1) setDropdownTarget("memory");
          else if (agentIndex === 2) setDropdownTarget("embedding");
        }
      } else if (activeSection === "connections") {
        const connIdx = CONNECTION_ITEMS.indexOf(connectionItem);
        const isGoogleSource = connectionItem === "gmail" || connectionItem === "calendar";
        const sourceEnabled = isGoogleSource && serverConfig?.sources?.[connectionItem]?.enabled;
        const hasAccountList = sourceEnabled && googleAccounts.length > 0;

        if (key.name === "up" || key.name === "k") {
          if (hasAccountList && selectedGoogleIndex > 0) {
            setSelectedGoogleIndex((i) => i - 1);
          } else if (connIdx > 0) {
            setConnectionItem(CONNECTION_ITEMS[connIdx - 1]);
            setSelectedGoogleIndex(0);
          }
        } else if (key.name === "down" || key.name === "j") {
          if (hasAccountList && selectedGoogleIndex < googleAccounts.length - 1) {
            setSelectedGoogleIndex((i) => i + 1);
          } else if (connIdx < CONNECTION_ITEMS.length - 1) {
            setConnectionItem(CONNECTION_ITEMS[connIdx + 1]);
            setSelectedGoogleIndex(0);
          }
        } else if (key.name === "return" || key.name === "space") {
          if (connectionItem === "vault") {
            handleStartVaultEdit();
          } else if (connectionItem === "browser") {
            setShowingBrowserDropdown(true);
          } else if (TOGGLEABLE_SOURCES.includes(connectionItem)) {
            handleToggleSource(connectionItem);
          }
        } else if (key.sequence === "a" && isGoogleSource && sourceEnabled) {
          handleAddGoogle();
        } else if ((key.sequence === "d" || key.name === "delete") && isGoogleSource && sourceEnabled) {
          handleRemoveGoogle();
        }
      } else if (activeSection === "appearance") {
        if (key.name === "up" || key.name === "k") {
          setAppearanceIndex((i) => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setAppearanceIndex((i) => Math.min(appearanceTotalItems - 1, i + 1));
        } else if (key.name === "return" || key.name === "space") {
          if (!isColorItem) {
            const item = APPEARANCE_ITEMS[appearanceIndex];
            onUpdate("ui", item.key, !settings.ui[item.key as keyof typeof settings.ui]);
          }
        } else if (key.name === "left" || key.name === "h") {
          if (isColorItem) {
            const currentIdx = colorOptions.indexOf(settings.ui.accentColor);
            const newIdx = (currentIdx - 1 + colorOptions.length) % colorOptions.length;
            onUpdate("ui", "accentColor", colorOptions[newIdx]);
          }
        } else if (key.name === "right" || key.name === "l") {
          if (isColorItem) {
            const currentIdx = colorOptions.indexOf(settings.ui.accentColor);
            const newIdx = (currentIdx + 1) % colorOptions.length;
            onUpdate("ui", "accentColor", colorOptions[newIdx]);
          }
        }
      } else if (activeSection === "limits") {
        if (key.name === "up" || key.name === "k") {
          setLimitsIndex((i) => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setLimitsIndex((i) => Math.min(limitsTotalItems - 1, i + 1));
        } else if (key.name === "left" || key.name === "h") {
          const item = LIMIT_ITEMS[limitsIndex];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val > item.min) onUpdate("agent", item.key, val - 1);
        } else if (key.name === "right" || key.name === "l") {
          const item = LIMIT_ITEMS[limitsIndex];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val < item.max) onUpdate("agent", item.key, val + 1);
        }
      }
    },
    [
      activeSection, agentIndex, appearanceIndex, limitsIndex,
      agentTotalItems, appearanceTotalItems, limitsTotalItems,
      isColorItem, settings, onUpdate, onClose, dropdownTarget,
      connectionItem, googleAccounts, selectedGoogleIndex, serverConfig,
      handleAddGoogle, handleRemoveGoogle, handleStartVaultEdit, handleToggleSource, actionInProgress,
    ]
  );

  // Vault editing keypress handler
  const handleVaultEditKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        handleCancelVaultEdit();
        return;
      }
      if (key.name === "return") {
        handleSaveVault();
        return;
      }
      handleVaultKey(key);
    },
    [handleVaultKey, handleSaveVault, handleCancelVaultEdit]
  );

  useKeypress(handleKeypress, { isActive: !dropdownTarget && !editingVault && !showingBrowserDropdown });
  useKeypress(handleVaultEditKeypress, { isActive: editingVault && !updatingVault });

  const handleEmbeddingConfirm = useCallback(async () => {
    if (!pendingEmbeddingModel || actionInProgress) return;
    setActionInProgress("Re-indexing...");
    try {
      const result = await updateEmbeddingModel(config, pendingEmbeddingModel);
      if (result.status === "reindexing") {
        setEmbeddingModel(pendingEmbeddingModel);
      }
    } catch {
      // Ignore errors
    } finally {
      setPendingEmbeddingModel(null);
      setActionInProgress(null);
    }
  }, [config, pendingEmbeddingModel, actionInProgress]);

  const handleEmbeddingKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape" || key.sequence === "n") {
        setPendingEmbeddingModel(null);
      } else if (key.name === "return" || key.sequence === "y") {
        handleEmbeddingConfirm();
      }
    },
    [handleEmbeddingConfirm]
  );

  useKeypress(handleEmbeddingKeypress, { isActive: !!pendingEmbeddingModel && !actionInProgress });

  // Confirmation dialog for embedding model change
  if (pendingEmbeddingModel) {
    return (
      <Box flexDirection="column" alignItems="center" paddingY={1}>
        <Panel title="CONFIRM RE-INDEX" width={Math.min(50, contentWidth)}>
          <Box flexDirection="column" paddingX={1} paddingY={1}>
            <Text color={colors.text.primary}>
              Change embedding model to:
            </Text>
            <Text color={accent} bold> {pendingEmbeddingModel}</Text>
            <Box marginTop={1}>
              <Text color={colors.status.warning}>
                ⚠ This will clear the search index and re-embed all content.
              </Text>
            </Box>
            {actionInProgress ? (
              <Box marginTop={1}>
                <Text color={colors.text.muted}>{actionInProgress}</Text>
              </Box>
            ) : (
              <Box marginTop={1}>
                <Text color={colors.text.disabled}>
                  y: confirm · n/Esc: cancel
                </Text>
              </Box>
            )}
          </Box>
        </Panel>
      </Box>
    );
  }

  if (dropdownTarget) {
    const isEmbedding = dropdownTarget === "embedding";
    const title = dropdownTarget === "chat" ? "Agent Model" : dropdownTarget === "memory" ? "Memory Model" : "Embedding Model";
    const currentModel = dropdownTarget === "chat" ? chatModel : dropdownTarget === "memory" ? memoryModel : embeddingModel;
    const modelList = isEmbedding ? embeddingModels : models;

    return (
      <Box flexDirection="column" alignItems="center" paddingY={1}>
        <ModelDropdown
          title={title}
          models={modelList}
          currentModel={currentModel}
          width={Math.min(50, contentWidth)}
          onSelect={(model) => {
            if (isEmbedding) {
              if (model !== embeddingModel) {
                setPendingEmbeddingModel(model);
              }
            } else {
              selectModel(dropdownTarget as "chat" | "memory", model);
            }
            setDropdownTarget(null);
          }}
          onClose={() => setDropdownTarget(null)}
        />
      </Box>
    );
  }

  if (showingBrowserDropdown) {
    return (
      <Box flexDirection="column" alignItems="center" paddingY={1}>
        <BrowserDropdown
          currentBrowser={serverConfig?.browser || null}
          width={Math.min(50, contentWidth)}
          onSelect={handleSelectBrowser}
          onClose={() => setShowingBrowserDropdown(false)}
        />
      </Box>
    );
  }

  const contentHeight = 12;

  return (
    <Panel title="PREFERENCES" width={contentWidth}>
      <Box flexDirection="row" marginTop={1}>
        {/* Sidebar */}
        <Box flexDirection="column" width={sidebarWidth}>
          {SECTION_IDS.map((section) => {
            const isActive = section === activeSection;
            return (
              <Text key={section}>
                <Text color={isActive ? accent : colors.text.disabled}>{isActive ? "▸ " : "  "}</Text>
                <Text color={isActive ? accent : colors.text.secondary} bold={isActive}>
                  {SECTION_LABELS[section]}
                </Text>
              </Text>
            );
          })}
        </Box>

        {/* Divider */}
        <Box flexDirection="column" width={1} marginX={1}>
          {Array.from({ length: contentHeight }).map((_, i) => (
            <Text key={i} color={colors.divider}>│</Text>
          ))}
        </Box>

        {/* Detail pane */}
        <Box flexDirection="column" width={detailWidth} minHeight={contentHeight}>
          {activeSection === "agent" && (
            <AgentSection
              chatModel={chatModel}
              memoryModel={memoryModel}
              embeddingModel={embeddingModel}
              selectedIndex={agentIndex}
              accent={accent}
              modelNameWidth={modelNameWidth}
            />
          )}

          {activeSection === "connections" && (
            <ConnectionsSection
              serverConfig={serverConfig}
              googleAccounts={googleAccounts}
              selectedItem={connectionItem}
              selectedGoogleIndex={selectedGoogleIndex}
              accent={accent}
              width={detailWidth}
              editingVault={editingVault}
              vaultPath={vaultPath}
              vaultCursorPos={vaultCursorPos}
              updatingVault={updatingVault}
              vaultError={vaultError}
              updatingBrowser={updatingBrowser}
              browserError={browserError}
            />
          )}

          {activeSection === "appearance" && (
            <AppearanceSection
              settings={settings.ui}
              selectedIndex={appearanceIndex}
              accent={accent}
            />
          )}

          {activeSection === "limits" && (
            <LimitsSection
              settings={settings.agent}
              selectedIndex={limitsIndex}
              accent={accent}
            />
          )}
        </Box>
      </Box>

      {actionInProgress && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>{actionInProgress}</Text>
        </Box>
      )}

      <Footer>Tab section · ↑↓ navigate · Enter select · ←→ adjust · Esc close</Footer>
    </Panel>
  );
}
