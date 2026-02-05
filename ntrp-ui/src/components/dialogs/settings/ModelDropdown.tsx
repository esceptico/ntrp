import { useState, useCallback, useMemo } from "react";
import { Box, Text } from "ink";
import { colors, brand, SelectionIndicator } from "../../ui/index.js";
import { useKeypress, type Key } from "../../../hooks/index.js";

interface ModelDropdownProps {
  title: string;
  models: string[];
  currentModel: string;
  onSelect: (model: string) => void;
  onClose: () => void;
  width: number;
}

function getShortModelName(model: string): string {
  if (!model) return "";
  const parts = model.split("/");
  return parts.length > 1 ? parts.slice(1).join("/") : model;
}

export function ModelDropdown({
  title,
  models,
  currentModel,
  onSelect,
  onClose,
  width,
}: ModelDropdownProps) {
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

  const maxVisible = 10;
  const scrollOffset = Math.max(0, Math.min(selectedIndex - Math.floor(maxVisible / 2), filteredModels.length - maxVisible));
  const visibleModels = filteredModels.slice(scrollOffset, scrollOffset + maxVisible);
  const hasScrollUp = scrollOffset > 0;
  const hasScrollDown = scrollOffset + maxVisible < filteredModels.length;

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        if (search) {
          setSearch("");
          setSelectedIndex(0);
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

      if (key.name === "backspace" || key.name === "delete") {
        setSearch((s) => s.slice(0, -1));
        setSelectedIndex(0);
        return;
      }

      if (key.insertable && key.sequence && !key.ctrl && !key.meta) {
        setSearch((s) => s + key.sequence);
        setSelectedIndex(0);
      }
    },
    [filteredModels, selectedIndex, search, onSelect, onClose]
  );

  useKeypress(handleKeypress, { isActive: true });

  const contentWidth = Math.max(0, width - 6);

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={brand.primary} width={width} paddingX={1}>
      {/* Title */}
      <Box justifyContent="center">
        <Text color={brand.primary} bold> {title} </Text>
      </Box>

      {/* Search */}
      <Box marginY={1}>
        <Text color={colors.text.muted}>/ </Text>
        <Text color={colors.text.primary}>{search}</Text>
        <Text color={brand.primary}>_</Text>
      </Box>

      {/* Scroll indicator up */}
      {hasScrollUp && (
        <Text color={colors.text.disabled}>  ↑ more</Text>
      )}

      {/* Model list */}
      <Box flexDirection="column">
        {visibleModels.map((model, idx) => {
          const actualIdx = scrollOffset + idx;
          const isSelected = actualIdx === selectedIndex;
          const isCurrent = model === currentModel;
          const shortName = getShortModelName(model);
          const displayName = shortName.length > contentWidth ? shortName.slice(0, contentWidth - 1) + "…" : shortName;

          return (
            <Text key={model}>
              <SelectionIndicator selected={isSelected} accent={brand.primary} />
              <Text
                color={isCurrent ? brand.primary : isSelected ? colors.text.primary : colors.text.secondary}
                bold={isCurrent}
              >
                {displayName}
              </Text>
              {isCurrent && <Text color={colors.text.muted}> •</Text>}
            </Text>
          );
        })}
        {filteredModels.length === 0 && (
          <Text color={colors.text.muted}>  No matches</Text>
        )}
      </Box>

      {/* Scroll indicator down */}
      {hasScrollDown && (
        <Text color={colors.text.disabled}>  ↓ more</Text>
      )}

      {/* Footer */}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>↑↓ move · Enter select · Esc {search ? "clear" : "back"}</Text>
      </Box>
    </Box>
  );
}
