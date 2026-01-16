import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, colors, accentColors, type AccentColor } from "../../ui/index.js";
import { getSupportedModels, updateModels } from "../../../api/client.js";
import { TabId, TAB_IDS, TAB_LABELS, BOOLEAN_ITEMS, NUMBER_ITEMS } from "./config.js";
import { BooleanRow, ColorPicker, ModelRow, NumberRow, colorOptions } from "./SettingsRows.js";

function useAccent(accentColor: AccentColor) {
  return useMemo(() => accentColors[accentColor].primary, [accentColor]);
}

interface SettingsDialogProps {
  config: Config;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onModelChange: (model: string) => void;
  onClose: () => void;
}

export function SettingsDialog({ config, settings, onUpdate, onModelChange, onClose }: SettingsDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const [activeTab, setActiveTab] = useState<TabId>("ui");
  const [uiIndex, setUiIndex] = useState(0);
  const [agentIndex, setAgentIndex] = useState(0);
  const accent = useAccent(settings.ui.accentColor);

  const contentWidth = Math.max(0, terminalWidth - 4);
  const modelNameWidth = Math.max(0, contentWidth - 10);

  const [models, setModels] = useState<string[]>([]);
  const [currentModel, setCurrentModel] = useState("");
  const [modelUpdating, setModelUpdating] = useState(false);

  useEffect(() => {
    getSupportedModels(config).then((result) => {
      setModels(result.models);
      setCurrentModel(result.current);
    }).catch(() => {});
  }, [config]);

  const uiTotalItems = BOOLEAN_ITEMS.length + 1;
  const isColorItem = activeTab === "ui" && uiIndex === BOOLEAN_ITEMS.length;

  const modelCount = models.length;
  const agentTotalItems = modelCount + NUMBER_ITEMS.length;
  const isModelItem = activeTab === "agent" && agentIndex < modelCount;
  const settingIdx = agentIndex - modelCount;

  const switchTab = useCallback((direction: 1 | -1) => {
    const idx = TAB_IDS.indexOf(activeTab);
    const next = (idx + direction + TAB_IDS.length) % TAB_IDS.length;
    setActiveTab(TAB_IDS[next]);
  }, [activeTab]);

  const selectModel = useCallback((modelName: string) => {
    if (modelUpdating || modelName === currentModel) return;
    setCurrentModel(modelName);
    onModelChange(modelName);
    setModelUpdating(true);
    updateModels(config, { chat_model: modelName })
      .catch(() => {})
      .finally(() => setModelUpdating(false));
  }, [config, currentModel, modelUpdating, onModelChange]);

  const handleKeypress = useCallback((key: Key) => {
    if (key.name === "escape" || key.name === "q") {
      onClose();
      return;
    }

    if (key.name === "tab") {
      switchTab(key.shift ? -1 : 1);
      return;
    }

    if (activeTab === "ui") {
      const maxIdx = uiTotalItems - 1;

      if (key.name === "up" || key.name === "k") {
        setUiIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setUiIndex((i) => Math.min(maxIdx, i + 1));
      } else if (key.name === "return" || key.name === "space") {
        if (!isColorItem) {
          const item = BOOLEAN_ITEMS[uiIndex];
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
    } else {
      const maxIdx = agentTotalItems - 1;

      if (key.name === "up" || key.name === "k") {
        setAgentIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setAgentIndex((i) => Math.min(maxIdx, i + 1));
      } else if (key.name === "return" || key.name === "space") {
        if (isModelItem) {
          selectModel(models[agentIndex]);
        }
      } else if (key.name === "left" || key.name === "h") {
        if (!isModelItem) {
          const item = NUMBER_ITEMS[settingIdx];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val > item.min) onUpdate("agent", item.key, val - 1);
        }
      } else if (key.name === "right" || key.name === "l") {
        if (!isModelItem) {
          const item = NUMBER_ITEMS[settingIdx];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val < item.max) onUpdate("agent", item.key, val + 1);
        }
      }
    }
  }, [
    onClose, switchTab, activeTab, uiIndex, uiTotalItems, isColorItem,
    agentIndex, agentTotalItems, isModelItem, settingIdx, settings, onUpdate, models, selectModel,
  ]);

  useKeypress(handleKeypress, { isActive: true });

  return (
    <Panel title="SETTINGS" width={contentWidth}>
      <Box marginBottom={1}>
        {TAB_IDS.map((tab, i) => (
          <Box key={tab} marginRight={1}>
            <Text
              color={tab === activeTab ? accent : colors.tabs.inactive}
              bold={tab === activeTab}
              inverse={tab === activeTab}
            >
              {" "}{TAB_LABELS[tab].toUpperCase()}{" "}
            </Text>
            {i < TAB_IDS.length - 1 && <Text color={colors.tabs.separator}>│</Text>}
          </Box>
        ))}
      </Box>

      <Box flexDirection="column" marginY={1} width={contentWidth} overflow="hidden">
        {activeTab === "ui" && (
          <>
            {BOOLEAN_ITEMS.map((item, index) => (
              <Box key={item.key}>
                <BooleanRow
                  item={item}
                  value={settings.ui[item.key as keyof typeof settings.ui] as boolean}
                  selected={index === uiIndex}
                  accent={accent}
                />
              </Box>
            ))}
            <Box marginTop={1}>
              <ColorPicker
                currentColor={settings.ui.accentColor}
                selected={isColorItem}
                accent={accent}
              />
            </Box>
          </>
        )}

        {activeTab === "agent" && (
          <>
            <Text color={colors.text.muted}>{"  "}Model</Text>
            {models.map((model, idx) => (
              <Box key={model}>
                <ModelRow
                  model={model}
                  isCurrent={model === currentModel}
                  selected={idx === agentIndex}
                  accent={accent}
                  maxWidth={modelNameWidth}
                />
              </Box>
            ))}

            {NUMBER_ITEMS.map((item, idx) => {
              const globalIdx = modelCount + idx;
              return (
                <Box key={item.key} marginTop={idx === 0 ? 1 : 0}>
                  <NumberRow
                    item={item}
                    value={settings.agent[item.key as keyof typeof settings.agent] as number}
                    selected={globalIdx === agentIndex}
                    accent={accent}
                  />
                </Box>
              );
            })}
          </>
        )}
      </Box>

      <Footer>Tab: switch │ ↑↓: navigate │ ←→: change │ Enter: select │ Esc: close</Footer>
    </Panel>
  );
}
