import { useState, useCallback, useMemo, useEffect } from "react";
import { colors, BaseSelectionList, Hints, truncateText } from "../../ui/index.js";
import { useKeypress, useAccentColor, type Key } from "../../../hooks/index.js";

interface ModelDropdownProps {
  models: string[];
  currentModel: string;
  onSelect: (model: string) => void;
  onClose: () => void;
  width: number;
}

const DEFAULT_MODEL_OPTION = "__default__";

function getShortModelName(model: string): string {
  if (model === DEFAULT_MODEL_OPTION) return "default";
  if (!model) return "";
  const parts = model.split("/");
  return parts.length > 1 ? parts.slice(1).join("/") : model;
}

export function ModelDropdown({
  models,
  currentModel,
  onSelect,
  onClose,
  width,
}: ModelDropdownProps) {
  const { accentValue } = useAccentColor();
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(() => {
    const idx = models.indexOf(currentModel);
    return idx >= 0 ? idx : 0;
  });

  const filteredModels = useMemo(() => {
    const validModels = models.filter(Boolean);
    if (!search) return validModels;
    const lower = search.toLowerCase();
    return validModels.filter((m) => m.toLowerCase().includes(lower));
  }, [models, search]);

  useEffect(() => {
    setSelectedIndex((i) => Math.max(0, Math.min(i, Math.max(0, filteredModels.length - 1))));
  }, [filteredModels.length]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        if (search) {
          setSearch("");
        } else {
          onClose();
        }
        return;
      }

      if (key.name === "return") {
        if (filteredModels.length > 0) {
          onSelect(filteredModels[selectedIndex]);
        }
        return;
      }

      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }

      if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(filteredModels.length - 1, i + 1));
        return;
      }
    },
    [filteredModels, selectedIndex, search, onSelect, onClose]
  );

  useKeypress(handleKeypress, { isActive: true });

  const contentWidth = Math.max(0, width - 4);

  return (
    <box flexDirection="column" width={width}>
      <box marginBottom={1} flexDirection="row">
        <text><span fg={colors.text.muted}>/ </span></text>
        <input
          value={search}
          onInput={(value) => {
            setSearch(value);
            setSelectedIndex(0);
          }}
          focused={true}
          textColor={colors.text.primary}
          focusedTextColor={colors.text.primary}
          cursorColor={accentValue}
          placeholder="search model"
          placeholderColor={colors.text.disabled}
          width={Math.max(10, width - 4)}
        />
      </box>

      {filteredModels.length === 0 ? (
        <text><span fg={colors.text.muted}>No matches</span></text>
      ) : (
        <BaseSelectionList
          items={filteredModels}
          selectedIndex={selectedIndex}
          visibleLines={10}
          showScrollArrows
          showCount
          showIndicator
          indicator="▶"
          renderItem={(model, ctx) => {
            const isCurrent = model === currentModel;
            const displayName = truncateText(getShortModelName(model), contentWidth);
            return (
              <text>
                {isCurrent ? (
                  <span fg={accentValue}><strong>{displayName}</strong></span>
                ) : (
                  <span fg={ctx.isSelected ? colors.text.primary : colors.text.secondary}>{displayName}</span>
                )}
                {isCurrent && <span fg={colors.text.muted}> •</span>}
              </text>
            );
          }}
        />
      )}

      {/* Footer */}
      <box marginTop={1}>
        <Hints items={[["↑↓", "move"], ["enter", "select"], ["esc", search ? "clear" : "back"]]} />
      </box>
    </box>
  );
}
