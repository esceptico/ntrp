import { useState, useCallback, useEffect, useRef } from "react";
import { useKeypress, type Key } from "../../hooks/index.js";
import { Dialog, BaseSelectionList, Hints, palettes, themeNames, type Theme } from "../ui/index.js";

interface ThemePickerProps {
  current: Theme;
  onSelect: (theme: Theme) => void;
  onClose: () => void;
}

const SWATCH = "█";

function ThemePreview({ theme }: { theme: Theme }) {
  const p = palettes[theme];
  return (
    <text>
      <span fg={p.background.base}>{SWATCH}</span>
      <span fg={p.background.element}>{SWATCH}</span>
      <span fg={p.text.primary}>{SWATCH}</span>
      <span fg={p.text.secondary}>{SWATCH}</span>
      <span fg={p.text.muted}>{SWATCH}</span>
      <span fg={p.accent.primary}>{SWATCH}</span>
      <span fg={p.border}>{SWATCH}</span>
    </text>
  );
}

export function ThemePicker({ current, onSelect, onClose }: ThemePickerProps) {
  const initialTheme = useRef(current);
  const [selectedIndex, setSelectedIndex] = useState(
    Math.max(0, themeNames.indexOf(current))
  );
  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        // revert to initial theme on cancel
        onSelect(initialTheme.current);
        onClose();
        return;
      }
      if (key.name === "return") {
        onSelect(themeNames[selectedIndex]);
        onClose();
        return;
      }
      if (key.name === "up" || (key.ctrl && key.name === "p")) {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || (key.ctrl && key.name === "n")) {
        setSelectedIndex((i) => Math.min(themeNames.length - 1, i + 1));
        return;
      }
    },
    [selectedIndex, onSelect, onClose]
  );

  useKeypress(handleKeypress, { isActive: true });

  // live preview: apply theme as user navigates
  useEffect(() => {
    const previewTheme = themeNames[selectedIndex];
    if (previewTheme !== current) {
      onSelect(previewTheme);
    }
  }, [selectedIndex, current, onSelect]);

  const footer = (
    <Hints items={[["↑↓", "navigate"], ["enter", "confirm"], ["esc", "cancel"]]} />
  );

  return (
    <Dialog title="Theme" size="medium" onClose={onClose} footer={footer}>
      {({ height }) => (
        <BaseSelectionList
          items={themeNames}
          selectedIndex={selectedIndex}
          visibleLines={height}
          showScrollArrows
          renderItem={(theme, ctx) => (
            <box flexDirection="row" gap={1}>
              <text>
                <span fg={ctx.colors.text}>
                  {theme}{theme === initialTheme.current ? " (current)" : ""}
                </span>
              </text>
              <ThemePreview theme={theme} />
            </box>
          )}
        />
      )}
    </Dialog>
  );
}
