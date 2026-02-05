import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, colors, accentColors, type AccentColor } from "../../ui/index.js";
import { getSupportedModels, updateModels } from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS, APPEARANCE_ITEMS, LIMIT_ITEMS } from "./config.js";
import { BooleanRow, ColorPicker, NumberRow, ModelSelector, colorOptions } from "./SettingsRows.js";
import { ModelDropdown } from "./ModelDropdown.js";

function useAccent(accentColor: AccentColor) {
  return useMemo(() => accentColors[accentColor].primary, [accentColor]);
}

type DropdownTarget = "chat" | "memory" | null;

interface SettingsDialogProps {
  config: Config;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onModelChange: (model: string) => void;
  onClose: () => void;
}

export function SettingsDialog({ config, settings, onUpdate, onModelChange, onClose }: SettingsDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const accent = useAccent(settings.ui.accentColor);

  const [activeSection, setActiveSection] = useState<SectionId>("agent");
  const [agentIndex, setAgentIndex] = useState(0);
  const [appearanceIndex, setAppearanceIndex] = useState(0);
  const [limitsIndex, setLimitsIndex] = useState(0);

  const [models, setModels] = useState<string[]>([]);
  const [chatModel, setChatModel] = useState("");
  const [memoryModel, setMemoryModel] = useState("");
  const [modelUpdating, setModelUpdating] = useState(false);
  const [dropdownTarget, setDropdownTarget] = useState<DropdownTarget>(null);

  const contentWidth = Math.max(0, terminalWidth - 4);
  const sidebarWidth = 16;
  const detailWidth = Math.max(0, contentWidth - sidebarWidth - 3);
  const modelNameWidth = Math.max(0, detailWidth - 20);

  useEffect(() => {
    getSupportedModels(config)
      .then((result) => {
        setModels(result.models);
        setChatModel(result.chat_model);
        setMemoryModel(result.memory_model);
      })
      .catch(() => {});
  }, [config]);

  const agentTotalItems = 2;
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

  const handleKeypress = useCallback(
    (key: Key) => {
      if (dropdownTarget) return;

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
          setDropdownTarget(agentIndex === 0 ? "chat" : "memory");
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
    ]
  );

  useKeypress(handleKeypress, { isActive: !dropdownTarget });

  if (dropdownTarget) {
    const title = dropdownTarget === "chat" ? "Agent Model" : "Memory Model";
    const currentModel = dropdownTarget === "chat" ? chatModel : memoryModel;

    return (
      <Box flexDirection="column" alignItems="center" paddingY={1}>
        <ModelDropdown
          title={title}
          models={models}
          currentModel={currentModel}
          width={Math.min(50, contentWidth)}
          onSelect={(model) => {
            selectModel(dropdownTarget, model);
            setDropdownTarget(null);
          }}
          onClose={() => setDropdownTarget(null)}
        />
      </Box>
    );
  }

  const contentHeight = 8;

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
              <Box marginTop={1}>
                <Text color={colors.text.disabled}>
                  Agent: reasoning + tools{"\n"}
                  Memory: extraction + recall
                </Text>
              </Box>
            </Box>
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

      <Footer>Tab section · ↑↓ navigate · Enter select · ←→ adjust · Esc close</Footer>
    </Panel>
  );
}
