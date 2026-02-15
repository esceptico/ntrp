import { useCallback, useEffect, useMemo, useState } from "react";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { Dialog, colors, accentColors, Hints, type AccentColor } from "../../ui/index.js";
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
  getDirectives,
  updateDirectives,
  type ServerConfig,
  type GoogleAccount,
} from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS, LIMIT_ITEMS, CONNECTION_ITEMS, TOGGLEABLE_SOURCES, type ConnectionItem } from "./config.js";
import { ModelDropdown } from "./ModelDropdown.js";
import { BrowserDropdown } from "./BrowserDropdown.js";
import { ConnectionsSection } from "./ConnectionsSection.js";
import { AgentSection, DirectivesSection, LimitsSection, NotifiersSection, SkillsSection } from "./sections/index.js";
import { useTextInput } from "../../../hooks/useTextInput.js";
import { useNotifiers } from "../../../hooks/useNotifiers.js";
import { useSkills } from "../../../hooks/useSkills.js";

function useAccent(accentColor: AccentColor) {
  return useMemo(() => accentColors[accentColor].primary, [accentColor]);
}

type DropdownTarget = "chat" | "explore" | "memory" | "embedding" | null;

interface SettingsDialogProps {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onModelChange: (type: "chat" | "explore" | "memory", model: string) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onRefreshIndexStatus: () => Promise<void>;
  onClose: () => void;
}

export function SettingsDialog({
  config,
  serverConfig,
  settings,
  onUpdate,
  onModelChange,
  onServerConfigChange,
  onRefreshIndexStatus,
  onClose,
}: SettingsDialogProps) {
  const accent = useAccent(settings.ui.accentColor);

  const [activeSection, setActiveSection] = useState<SectionId>("agent");
  const [agentIndex, setAgentIndex] = useState(0);
  const [limitsIndex, setLimitsIndex] = useState(0);

  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const [editingVault, setEditingVault] = useState(false);
  const [vaultPath, setVaultPath] = useState(serverConfig?.vault_path || "");
  const [vaultCursorPos, setVaultCursorPos] = useState(0);
  const [updatingVault, setUpdatingVault] = useState(false);
  const [vaultError, setVaultError] = useState<string | null>(null);

  const [showingBrowserDropdown, setShowingBrowserDropdown] = useState(false);
  const [updatingBrowser, setUpdatingBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  const [models, setModels] = useState<string[]>([]);
  const [chatModel, setChatModel] = useState(serverConfig?.chat_model ?? "");
  const [exploreModel, setExploreModel] = useState(serverConfig?.explore_model ?? "");
  const [memoryModel, setMemoryModel] = useState(serverConfig?.memory_model ?? "");
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [embeddingModel, setEmbeddingModel] = useState(serverConfig?.embedding_model ?? "");
  const [modelUpdating, setModelUpdating] = useState(false);
  const [dropdownTarget, setDropdownTarget] = useState<DropdownTarget>(null);
  const [pendingEmbeddingModel, setPendingEmbeddingModel] = useState<string | null>(null);

  const [directivesContent, setDirectivesContent] = useState("");
  const [directivesSaved, setDirectivesSaved] = useState("");
  const [directivesCursorPos, setDirectivesCursorPos] = useState(0);
  const [editingDirectives, setEditingDirectives] = useState(false);
  const [savingDirectives, setSavingDirectives] = useState(false);

  const notifiers = useNotifiers(config);
  const skills = useSkills(config);

  useEffect(() => {
    getSupportedModels(config)
      .then((result) => {
        setModels(result.models);
        if (!chatModel) setChatModel(result.chat_model);
        if (!exploreModel) setExploreModel(result.explore_model);
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

  useEffect(() => {
    getGoogleAccounts(config)
      .then((result) => setGoogleAccounts(result.accounts))
      .catch(() => {});
    getDirectives(config)
      .then((result) => {
        setDirectivesContent(result.content);
        setDirectivesSaved(result.content);
      })
      .catch(() => {});
  }, [config]);

  const agentTotalItems = 4;
  const limitsTotalItems = LIMIT_ITEMS.length;

  const selectModel = useCallback(
    (modelType: "chat" | "explore" | "memory", modelName: string) => {
      if (modelUpdating) return;
      if (modelType === "chat") {
        if (modelName === chatModel) return;
        setChatModel(modelName);
        onModelChange("chat", modelName);
        setModelUpdating(true);
        updateConfig(config, { chat_model: modelName })
          .catch(() => {})
          .finally(() => setModelUpdating(false));
      } else if (modelType === "explore") {
        if (modelName === exploreModel) return;
        setExploreModel(modelName);
        onModelChange("explore", modelName);
        setModelUpdating(true);
        updateConfig(config, { explore_model: modelName })
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
    [config, chatModel, exploreModel, memoryModel, modelUpdating, onModelChange]
  );

  const handleAddGoogle = useCallback(async () => {
    if (actionInProgress) return;
    setActionInProgress("Adding account...");
    try {
      await addGoogleAccount(config);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
    } catch {
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
    } finally {
      setActionInProgress(null);
    }
  }, [config, googleAccounts, selectedGoogleIndex, actionInProgress]);

  const { handleKey: handleDirectivesKey } = useTextInput({
    text: directivesContent,
    cursorPos: directivesCursorPos,
    setText: setDirectivesContent,
    setCursorPos: setDirectivesCursorPos,
  });

  const handleSaveDirectives = useCallback(async () => {
    if (savingDirectives) return;
    setSavingDirectives(true);
    try {
      const result = await updateDirectives(config, directivesContent);
      setDirectivesSaved(result.content);
      setDirectivesContent(result.content);
      setEditingDirectives(false);
    } catch {
    } finally {
      setSavingDirectives(false);
    }
  }, [config, directivesContent, savingDirectives]);

  const handleCancelDirectives = useCallback(() => {
    setDirectivesContent(directivesSaved);
    setDirectivesCursorPos(0);
    setEditingDirectives(false);
  }, [directivesSaved]);

  const handleStartDirectivesEdit = useCallback(() => {
    setDirectivesCursorPos(directivesContent.length);
    setEditingDirectives(true);
  }, [directivesContent]);

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
    } finally {
      setActionInProgress(null);
    }
  }, [config, serverConfig, actionInProgress, onServerConfigChange]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (dropdownTarget || actionInProgress) return;

      if (key.name === "escape" || key.name === "q") {
        if (activeSection === "notifiers" && notifiers.mode !== "list") {
          notifiers.handleKeypress(key);
          return;
        }
        if (activeSection === "skills" && skills.mode !== "list") {
          skills.handleKeypress(key);
          return;
        }
        if (activeSection === "directives" && editingDirectives) {
          handleCancelDirectives();
          return;
        }
        onClose();
        return;
      }

      if (key.name === "tab") {
        if (activeSection === "notifiers" && notifiers.mode !== "list") return;
        if (activeSection === "skills" && skills.mode !== "list") return;
        if (activeSection === "directives" && editingDirectives) return;
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
          else if (agentIndex === 1) setDropdownTarget("explore");
          else if (agentIndex === 2) setDropdownTarget("memory");
          else if (agentIndex === 3) setDropdownTarget("embedding");
        }
      } else if (activeSection === "directives") {
        if (editingDirectives) {
          if (key.name === "s" && key.ctrl) {
            handleSaveDirectives();
          } else {
            handleDirectivesKey(key);
          }
        } else if (key.name === "return" || key.name === "space") {
          handleStartDirectivesEdit();
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
      } else if (activeSection === "skills") {
        skills.handleKeypress(key);
      } else if (activeSection === "notifiers") {
        notifiers.handleKeypress(key);
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
      activeSection, agentIndex, limitsIndex,
      agentTotalItems, limitsTotalItems,
      settings, onUpdate, onClose, dropdownTarget,
      connectionItem, googleAccounts, selectedGoogleIndex, serverConfig,
      handleAddGoogle, handleRemoveGoogle, handleStartVaultEdit, handleToggleSource, actionInProgress,
      notifiers, skills,
      editingDirectives, handleDirectivesKey, handleSaveDirectives, handleCancelDirectives, handleStartDirectivesEdit,
    ]
  );

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
        const updatedConfig = await getServerConfig(config);
        onServerConfigChange(updatedConfig);
        await onRefreshIndexStatus();
        onClose();
      }
    } catch {
    } finally {
      setPendingEmbeddingModel(null);
      setActionInProgress(null);
    }
  }, [config, pendingEmbeddingModel, actionInProgress, onServerConfigChange, onRefreshIndexStatus, onClose]);

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

  if (pendingEmbeddingModel) {
    return (
      <Dialog title="CONFIRM RE-INDEX" size="medium" onClose={() => setPendingEmbeddingModel(null)}>
        {() => (
          <box flexDirection="column">
            <text><span fg={colors.text.primary}>Change embedding model to:</span></text>
            <text><span fg={accent}><strong> {pendingEmbeddingModel}</strong></span></text>
            <box marginTop={1}>
              <text><span fg={colors.status.warning}>⚠ This will clear the search index and re-embed all content.</span></text>
            </box>
            {actionInProgress ? (
              <box marginTop={1}>
                <text><span fg={colors.text.muted}>{actionInProgress}</span></text>
              </box>
            ) : (
              <box marginTop={1}>
                <Hints items={[["y", "confirm"], ["n/esc", "cancel"]]} />
              </box>
            )}
          </box>
        )}
      </Dialog>
    );
  }

  if (dropdownTarget) {
    const isEmbedding = dropdownTarget === "embedding";
    const title = dropdownTarget === "chat" ? "Agent Model" : dropdownTarget === "explore" ? "Explore Model" : dropdownTarget === "memory" ? "Memory Model" : "Embedding Model";
    const currentModel = dropdownTarget === "chat" ? chatModel : dropdownTarget === "explore" ? exploreModel : dropdownTarget === "memory" ? memoryModel : embeddingModel;
    const modelList = isEmbedding ? embeddingModels : models;

    return (
      <Dialog title={title} size="medium" onClose={() => setDropdownTarget(null)}>
        {({ width }) => (
          <ModelDropdown
            models={modelList}
            currentModel={currentModel}
            width={Math.min(50, width)}
            onSelect={(model) => {
              if (isEmbedding) {
                if (model !== embeddingModel) {
                  setPendingEmbeddingModel(model);
                }
              } else {
                selectModel(dropdownTarget as "chat" | "explore" | "memory", model);
              }
              setDropdownTarget(null);
            }}
            onClose={() => setDropdownTarget(null)}
          />
        )}
      </Dialog>
    );
  }

  if (showingBrowserDropdown) {
    return (
      <Dialog title="Browser" size="medium" onClose={() => setShowingBrowserDropdown(false)}>
        {({ width }) => (
          <BrowserDropdown
            currentBrowser={serverConfig?.browser || null}
            width={Math.min(50, width)}
            onSelect={handleSelectBrowser}
            onClose={() => setShowingBrowserDropdown(false)}
          />
        )}
      </Dialog>
    );
  }

  return (
    <Dialog
      title="PREFERENCES"
      size="large"
      onClose={onClose}
      footer={<Hints items={[["tab", "section"], ["↑↓", "navigate"], ["enter", "select"], ["←→", "adjust"], ["esc", "close"]]} />}
    >
      {({ width, height }) => {
        const sidebarWidth = 16;
        const detailWidth = Math.max(0, width - sidebarWidth - 3);
        const modelNameWidth = Math.max(0, detailWidth - 20);
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
                {activeSection === "agent" && (
                  <AgentSection
                    chatModel={chatModel}
                    exploreModel={exploreModel}
                    memoryModel={memoryModel}
                    embeddingModel={embeddingModel}
                    selectedIndex={agentIndex}
                    accent={accent}
                    modelNameWidth={modelNameWidth}
                  />
                )}

                {activeSection === "directives" && (
                  <DirectivesSection
                    content={directivesContent}
                    cursorPos={directivesCursorPos}
                    editing={editingDirectives}
                    saving={savingDirectives}
                    accent={accent}
                    height={contentHeight}
                  />
                )}

                {activeSection === "skills" && (
                  <SkillsSection skills={skills} accent={accent} width={detailWidth} />
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

                {activeSection === "notifiers" && (
                  <NotifiersSection notifiers={notifiers} accent={accent} />
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

            {actionInProgress && (
              <box marginTop={1}>
                <text><span fg={colors.status.warning}>{actionInProgress}</span></text>
              </box>
            )}
          </>
        );
      }}
    </Dialog>
  );
}
