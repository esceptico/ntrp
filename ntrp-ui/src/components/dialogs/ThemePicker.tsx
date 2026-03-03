import { useState, useRef, useCallback } from "react";
import { DialogSelect } from "../ui/index.js";
import { colors, setTheme, themeNames, accentNames, accents, palettes, isBaseTheme, type Theme, type AccentColor } from "../ui/colors.js";
import { useKeypress, type Key } from "../../hooks/index.js";

interface ThemePickerProps {
  currentTheme: Theme;
  currentAccent: AccentColor;
  onSelect: (theme: Theme, accent: AccentColor) => void;
  onClose: () => void;
}

export function ThemePicker({ currentTheme, currentAccent, onSelect, onClose }: ThemePickerProps) {
  const themeBeforeRef = useRef(currentTheme);
  const accentBeforeRef = useRef(currentAccent);
  const [previewAccent, setPreviewAccent] = useState<AccentColor>(currentAccent);
  const previewAccentRef = useRef(currentAccent);
  const focusedThemeRef = useRef(currentTheme);

  const handleKeypress = useCallback((key: Key) => {
    if (key.name === "left" || key.name === "right") {
      if (!isBaseTheme(focusedThemeRef.current)) return;
      const delta = key.name === "right" ? 1 : -1;
      const idx = accentNames.indexOf(previewAccentRef.current);
      const next = accentNames[(idx + delta + accentNames.length) % accentNames.length]!;
      previewAccentRef.current = next;
      setPreviewAccent(next);
      setTheme(focusedThemeRef.current as Theme, next);
    }
  }, []);

  useKeypress(handleKeypress, { isActive: true });

  return (
    <DialogSelect<string>
      title="Theme"
      options={themeNames.map(t => ({
        value: t,
        title: t,
        indicator: t === currentTheme ? "\u25CF" : undefined,
      }))}
      initialIndex={Math.max(0, themeNames.indexOf(currentTheme))}
      onMove={(opt) => {
        focusedThemeRef.current = opt.value;
        setTheme(opt.value as Theme, previewAccentRef.current);
      }}
      onSelect={(opt) => {
        onSelect(opt.value as Theme, previewAccentRef.current);
      }}
      onClose={() => {
        setTheme(themeBeforeRef.current, accentBeforeRef.current);
        onClose();
      }}
      renderItem={(opt, ctx) => {
        const S = "\u2588";
        const p = palettes[opt.value as Theme];
        const showAccent = ctx.isSelected && isBaseTheme(opt.value);
        const ac = isBaseTheme(opt.value)
          ? accents[previewAccent]?.[opt.value as "dark" | "light"]?.primary ?? p.accent.primary
          : p.accent.primary;
        return (
          <box flexDirection="row" flexGrow={1}>
            <box flexGrow={1}>
              <text>
                <span fg={ctx.colors.text}>{opt.title}</span>
                {showAccent && <span fg={colors.text.muted}>{" \u2190\u2192 "}{previewAccent}</span>}
              </text>
            </box>
            <box flexShrink={0}>
              <text>
                <span fg={ac}>{S}</span>
                <span fg={p.status.success}>{S}</span>
                <span fg={p.status.error}>{S}</span>
                <span fg={p.status.warning}>{S}</span>
              </text>
            </box>
          </box>
        );
      }}
    />
  );
}
