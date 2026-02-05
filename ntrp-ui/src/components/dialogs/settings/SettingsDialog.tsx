import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, colors, accentColors, type AccentColor } from "../../ui/index.js";
import {
  getSupportedModels,
  updateModels,
  getGmailAccounts,
  addGmailAccount,
  removeGmailAccount,
  getEmbeddingModels,
  updateEmbeddingModel,
  type ServerConfig,
  type GmailAccount,
} from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS, APPEARANCE_ITEMS, LIMIT_ITEMS, CONNECTION_ITEMS, type ConnectionItem } from "./config.js";
import { BooleanRow, ColorPicker, NumberRow, ModelSelector, colorOptions } from "./SettingsRows.js";
import { ModelDropdown } from "./ModelDropdown.js";
import { ConnectionsSection } from "./ConnectionsSection.js";

function useAccent(accentColor: AccentColor) {
  return useMemo(() => accentColors[accentColor].primary, [accentColor]);
}

type DropdownTarget = "chat" | "memory" | "embedding" | null;

interface SettingsDialogProps {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onModelChange: (model: string) => void;
  onClose: () => void;
  onStatusMessage?: (msg: string) => void;
}

export function SettingsDialog({
  config,
  serverConfig,
  settings,
  onUpdate,
  onModelChange,
  onClose,
  onStatusMessage,
}: SettingsDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const accent = useAccent(settings.ui.accentColor);

  const [activeSection, setActiveSection] = useState<SectionId>("agent");
  const [agentIndex, setAgentIndex] = useState(0);
  const [appearanceIndex, setAppearanceIndex] = useState(0);
  const [limitsIndex, setLimitsIndex] = useState(0);

  // Connections state
  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GmailAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

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
    getGmailAccounts(config)
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
        onModelChange(modelName);
        setModelUpdating(true);
        updateModels(config, { chat_model: modelName })
          .catch(() => {})
          .finally(() => setModelUpdating(false));
      } else {
        if (modelName === memoryModel) return;
        setMemoryModel(modelName);
        setModelUpdating(true);
        updateModels(config, { memory_model: modelName })
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
      const result = await addGmailAccount(config);
      onStatusMessage?.(`✓ Connected: ${result.email}`);
      const accounts = await getGmailAccounts(config);
      setGoogleAccounts(accounts.accounts);
    } catch (e) {
      onStatusMessage?.(`✗ Failed: ${e}`);
    } finally {
      setActionInProgress(null);
    }
  }, [config, actionInProgress, onStatusMessage]);

  const handleRemoveGoogle = useCallback(async () => {
    if (actionInProgress || googleAccounts.length === 0) return;
    const account = googleAccounts[selectedGoogleIndex];
    if (!account) return;

    setActionInProgress("Removing...");
    try {
      const result = await removeGmailAccount(config, account.token_file);
      onStatusMessage?.(`✓ Removed: ${result.email || account.token_file}`);
      const accounts = await getGmailAccounts(config);
      setGoogleAccounts(accounts.accounts);
      setSelectedGoogleIndex(Math.max(0, selectedGoogleIndex - 1));
    } catch (e) {
      onStatusMessage?.(`✗ Failed: ${e}`);
    } finally {
      setActionInProgress(null);
    }
  }, [config, googleAccounts, selectedGoogleIndex, actionInProgress, onStatusMessage]);

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

        if (key.name === "up" || key.name === "k") {
          if (connectionItem === "google" && googleAccounts.length > 0 && selectedGoogleIndex > 0) {
            setSelectedGoogleIndex((i) => i - 1);
          } else if (connIdx > 0) {
            setConnectionItem(CONNECTION_ITEMS[connIdx - 1]);
          }
        } else if (key.name === "down" || key.name === "j") {
          if (connectionItem === "google" && googleAccounts.length > 0 && selectedGoogleIndex < googleAccounts.length - 1) {
            setSelectedGoogleIndex((i) => i + 1);
          } else if (connIdx < CONNECTION_ITEMS.length - 1) {
            setConnectionItem(CONNECTION_ITEMS[connIdx + 1]);
          }
        } else if (key.sequence === "a" && connectionItem === "google") {
          handleAddGoogle();
        } else if ((key.sequence === "d" || key.name === "delete") && connectionItem === "google") {
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
      connectionItem, googleAccounts, selectedGoogleIndex,
      handleAddGoogle, handleRemoveGoogle, actionInProgress,
    ]
  );

  useKeypress(handleKeypress, { isActive: !dropdownTarget });

  const handleEmbeddingConfirm = useCallback(async () => {
    if (!pendingEmbeddingModel || actionInProgress) return;
    setActionInProgress("Re-indexing...");
    try {
      const result = await updateEmbeddingModel(config, pendingEmbeddingModel);
      if (result.status === "reindexing") {
        setEmbeddingModel(pendingEmbeddingModel);
        onStatusMessage?.(`✓ Switched to ${pendingEmbeddingModel}, re-indexing started`);
      } else if (result.status === "unchanged") {
        onStatusMessage?.("Model unchanged");
      } else {
        onStatusMessage?.(`✗ ${result.message || "Failed"}`);
      }
    } catch (e) {
      onStatusMessage?.(`✗ Failed: ${e}`);
    } finally {
      setPendingEmbeddingModel(null);
      setActionInProgress(null);
    }
  }, [config, pendingEmbeddingModel, actionInProgress, onStatusMessage]);

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

  const contentHeight = 10;

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
            <Box flexDirection="column">
              <ModelSelector
                label="Agent"
                currentModel={chatModel}
                selected={agentIndex === 0}
                accent={accent}
                maxWidth={modelNameWidth}
              />
              <ModelSelector
                label="Memory"
                currentModel={memoryModel}
                selected={agentIndex === 1}
                accent={accent}
                maxWidth={modelNameWidth}
              />
              <ModelSelector
                label="Embedding"
                currentModel={embeddingModel}
                selected={agentIndex === 2}
                accent={accent}
                maxWidth={modelNameWidth}
              />
              <Box marginTop={1}>
                <Text color={colors.text.disabled}>
                  Agent: reasoning + tools{"\n"}
                  Memory: extraction + recall{"\n"}
                  Embedding: search vectors
                </Text>
              </Box>
            </Box>
          )}

          {activeSection === "connections" && (
            <ConnectionsSection
              serverConfig={serverConfig}
              googleAccounts={googleAccounts}
              selectedItem={connectionItem}
              selectedGoogleIndex={selectedGoogleIndex}
              accent={accent}
              width={detailWidth}
            />
          )}

          {activeSection === "appearance" && (
            <Box flexDirection="column">
              {APPEARANCE_ITEMS.map((item, index) => (
                <BooleanRow
                  key={item.key}
                  item={item}
                  value={settings.ui[item.key as keyof typeof settings.ui] as boolean}
                  selected={index === appearanceIndex}
                  accent={accent}
                />
              ))}
              <Box marginTop={1}>
                <ColorPicker
                  currentColor={settings.ui.accentColor}
                  selected={isColorItem}
                  accent={accent}
                />
              </Box>
            </Box>
          )}

          {activeSection === "limits" && (
            <Box flexDirection="column">
              {LIMIT_ITEMS.map((item, idx) => (
                <NumberRow
                  key={item.key}
                  item={item}
                  value={settings.agent[item.key as keyof typeof settings.agent] as number}
                  selected={idx === limitsIndex}
                  accent={accent}
                />
              ))}
            </Box>
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
