import { useCallback, useState } from "react";
import { Box, Text } from "ink";
import { Panel, Footer, colors } from "../../ui/index.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { BaseSelectionList } from "../../ui/list/BaseSelectionList.js";

const BROWSER_OPTIONS = [
  { value: "chrome", label: "Chrome" },
  { value: "safari", label: "Safari" },
  { value: "arc", label: "Arc" },
  { value: null, label: "None (disable)" },
] as const;

type BrowserValue = "chrome" | "safari" | "arc" | null;

interface BrowserDropdownProps {
  currentBrowser: string | null;
  width: number;
  onSelect: (browser: BrowserValue) => void;
  onClose: () => void;
}

export function BrowserDropdown({
  currentBrowser,
  width,
  onSelect,
  onClose,
}: BrowserDropdownProps) {
  const [selectedIndex, setSelectedIndex] = useState(() => {
    const idx = BROWSER_OPTIONS.findIndex((opt) => opt.value === currentBrowser);
    return idx >= 0 ? idx : 0;
  });

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape" || key.name === "q") {
        onClose();
        return;
      }

      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(BROWSER_OPTIONS.length - 1, i + 1));
      } else if (key.name === "return" || key.name === "space") {
        onSelect(BROWSER_OPTIONS[selectedIndex].value);
      }
    },
    [selectedIndex, onSelect, onClose]
  );

  useKeypress(handleKeypress, { isActive: true });

  return (
    <Panel title="SELECT BROWSER" width={width}>
      <Box marginTop={1}>
        <BaseSelectionList
          items={BROWSER_OPTIONS}
          selectedIndex={selectedIndex}
          renderItem={(option, context) => {
            const isCurrent = option.value === currentBrowser;
            return (
              <Text color={context.isSelected ? context.colors.indicator : isCurrent ? colors.text.primary : colors.text.secondary}>
                {option.label}
                {isCurrent && <Text color={colors.text.disabled}> (current)</Text>}
              </Text>
            );
          }}
        />
      </Box>
      <Footer>↑↓ navigate · Enter select · Esc cancel</Footer>
    </Panel>
  );
}
