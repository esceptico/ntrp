import React, { useState, useCallback, useRef, useMemo, memo, useEffect } from "react";
import { Box, Text, useStdout } from "ink";
import type { SlashCommand } from "../../types.js";
import { colors } from "../ui/colors.js";
import { useKeypress, useAccentColor, type Key } from "../../hooks/index.js";
import { AutocompleteList } from "./AutocompleteList.js";
import { HelpPanel } from "./HelpPanel.js";

function formatModel(model?: string) {
  if (!model) return "";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

export interface InputAreaProps {
  onSubmit: (v: string) => void;
  disabled: boolean;
  focus: boolean;
  commands: readonly SlashCommand[];
  queueCount?: number;
  skipApprovals?: boolean;
  chatModel?: string;
  indexStatus?: { indexing: boolean; progress: { total: number; done: number } } | null;
}

export const InputArea = memo(function InputArea({
  onSubmit,
  disabled,
  focus,
  commands,
  queueCount = 0,
  skipApprovals = false,
  chatModel,
  indexStatus = null,
}: InputAreaProps) {
  const { stdout } = useStdout();
  const columns = stdout?.columns ?? 80;
  const divider = "─".repeat(columns - 2);
  const { accentValue } = useAccentColor();

  const [value, setValue] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [escHint, setEscHint] = useState(false);

  // Refs for stable access in callbacks
  const cursorRef = useRef(0);
  cursorRef.current = cursorPos;
  const valueRef = useRef(value);
  valueRef.current = value;
  const escPendingRef = useRef(false);
  const escTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
    };
  }, []);

  const resetInput = useCallback(() => {
    if (escTimeoutRef.current) {
      clearTimeout(escTimeoutRef.current);
      escTimeoutRef.current = null;
    }
    setValue("");
    setCursorPos(0);
    setSelectedIndex(0);
    escPendingRef.current = false;
    setEscHint(false);
  }, []);

  // Get filtered commands for autocomplete
  const filteredCommands = useMemo(() => {
    if (!value.startsWith("/")) return [];
    const query = value.slice(1).toLowerCase();
    if (!query) return commands;
    return commands.filter(
      (cmd) => cmd.name.toLowerCase().startsWith(query) || cmd.name.toLowerCase().includes(query)
    );
  }, [commands, value]);

  const showAutocomplete = value.startsWith("/") && filteredCommands.length > 0;
  const showHelp = value === "?";

  // Word boundary navigation helpers (use ref for fresh value)
  const findPrevWordBoundary = useCallback((pos: number) => {
    const v = valueRef.current;
    let p = pos - 1;
    while (p > 0 && /\s/.test(v[p])) p--;
    while (p > 0 && /\S/.test(v[p - 1])) p--;
    return Math.max(0, p);
  }, []);

  const findNextWordBoundary = useCallback((pos: number) => {
    const v = valueRef.current;
    let p = pos;
    while (p < v.length && /\S/.test(v[p])) p++;
    while (p < v.length && /\s/.test(v[p])) p++;
    return p;
  }, []);

  const moveCursor = (newPos: number) => {
    setCursorPos(newPos);
    cursorRef.current = newPos;
  };

  const insertAt = (pos: number, text: string) => {
    setValue((v) => v.slice(0, pos) + text + v.slice(pos));
    moveCursor(pos + text.length);
    setSelectedIndex(0);
  };

  const handleKeypress = useCallback(
    (key: Key) => {
      if (disabled) return;
      const pos = cursorRef.current;

      // Paste
      if (key.isPasted && key.sequence) {
        insertAt(pos, key.sequence);
        return;
      }

      // Autocomplete navigation
      if (showAutocomplete) {
        if (key.name === "up") { setSelectedIndex((i) => Math.max(0, i - 1)); return; }
        if (key.name === "down") { setSelectedIndex((i) => Math.min(filteredCommands.length - 1, i + 1)); return; }
        if (key.name === "tab" && filteredCommands[selectedIndex]) {
          const cmd = filteredCommands[selectedIndex];
          const newPos = cmd.name.length + 2;
          setValue(`/${cmd.name} `);
          moveCursor(newPos);
          setSelectedIndex(0);
          return;
        }
      }

      // Escape: double-tap to clear input
      if (key.name === "escape") {
        if (!value) return;
        if (escPendingRef.current) {
          resetInput();
        } else {
          escPendingRef.current = true;
          setEscHint(true);
          if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
          escTimeoutRef.current = setTimeout(() => {
            escPendingRef.current = false;
            setEscHint(false);
          }, 2000);
        }
        return;
      }

      if (key.name === "return") {
        // Newline: Shift+Enter (kitty protocol) or trailing backslash (fallback)
        // Shift+Enter works in: iTerm2, Kitty, Alacritty, WezTerm
        // Backslash fallback for: Cursor terminal, Terminal.app
        if (key.shift || value.endsWith("\\")) {
          if (value.endsWith("\\")) {
            // Remove backslash and insert newline at the end
            const newValue = value.slice(0, -1) + "\n";
            setValue(newValue);
            moveCursor(newValue.length);
          } else {
            insertAt(pos, "\n");
          }
          return;
        }
        if (showAutocomplete && filteredCommands[selectedIndex]) {
          onSubmit(`/${filteredCommands[selectedIndex].name}`);
          resetInput();
          return;
        }
        if (value.trim()) { onSubmit(value); resetInput(); }
        return;
      }

      // Delete word backward: Option+Backspace (requires terminal config) or Ctrl+W (universal)
      // Option+Backspace requires: macOptionIsMeta (Cursor) or "Option as Esc+" (iTerm2)
      if ((key.name === "backspace" && key.meta) || (key.name === "w" && key.ctrl)) {
        if (pos === 0) return;
        const newPos = findPrevWordBoundary(pos);
        setValue((v) => v.slice(0, newPos) + v.slice(pos));
        moveCursor(newPos);
        return;
      }
      if (key.name === "backspace") {
        if (pos > 0) {
          setValue((v) => v.slice(0, pos - 1) + v.slice(pos));
          moveCursor(pos - 1);
        }
        return;
      }
      if (key.name === "delete") {
        setValue((v) => v.slice(0, pos) + v.slice(pos + 1));
        return;
      }
      if (key.name === "k" && key.ctrl) {
        setValue((v) => v.slice(0, pos));
        return;
      }
      if (key.name === "u" && key.ctrl) {
        setValue((v) => v.slice(pos));
        moveCursor(0);
        return;
      }
      // Navigation - must sync cursorRef for next keypress
      // Word navigation: meta+arrows (Mac), ctrl+arrows (Linux/Windows)
      if ((key.name === "left" && key.meta) || (key.name === "left" && key.ctrl)) {
        moveCursor(findPrevWordBoundary(pos));
        return;
      }
      if ((key.name === "right" && key.meta) || (key.name === "right" && key.ctrl)) {
        moveCursor(findNextWordBoundary(pos));
        return;
      }
      if (key.name === "b" && key.meta) {
        moveCursor(findPrevWordBoundary(pos));
        return;
      }
      if (key.name === "f" && key.meta) {
        moveCursor(findNextWordBoundary(pos));
        return;
      }
      if (key.name === "left") {
        moveCursor(Math.max(0, pos - 1));
        return;
      }
      if (key.name === "right") {
        moveCursor(Math.min(value.length, pos + 1));
        return;
      }
      if (key.name === "home" || (key.name === "a" && key.ctrl)) {
        moveCursor(0);
        return;
      }
      if (key.name === "end" || (key.name === "e" && key.ctrl)) {
        moveCursor(value.length);
        return;
      }

      // Insert printable
      if (key.insertable && key.sequence && !key.ctrl && !key.meta) {
        insertAt(pos, key.sequence);
      }
    },
    [disabled, value, onSubmit, showAutocomplete, filteredCommands, selectedIndex, resetInput]
  );

  // Always active when focused - even during streaming (messages get queued)
  useKeypress(handleKeypress, { isActive: focus });

  // Simple cursor rendering with inline cursor
  const beforeCursor = value.slice(0, cursorPos);
  const atCursor = value[cursorPos] || " ";
  const afterCursor = value.slice(cursorPos + 1);

  return (
    <Box flexDirection="column">
      {/* Top divider */}
      <Text color={colors.divider}>{divider}</Text>

      {/* Input row - single Text element */}
      <Text>
        <Text color={accentValue} bold>{">"}</Text>
        <Text> </Text>
        <Text>{beforeCursor}</Text>
        <Text inverse>{atCursor}</Text>
        <Text>{afterCursor}</Text>
      </Text>

      {/* Bottom divider */}
      <Text color={colors.divider}>{divider}</Text>

      {/* Footer */}
      {!showAutocomplete && !showHelp && (
        <Box flexDirection="column" width={columns - 2} overflow="hidden">
          {chatModel && <Text dimColor>{formatModel(chatModel)}</Text>}
          <Text>
            {skipApprovals && <Text color={colors.status.warning} bold>skip approvals</Text>}
            {indexStatus?.indexing && <Text dimColor>{skipApprovals ? "  ·  " : ""}indexing {indexStatus.progress.done}/{indexStatus.progress.total}</Text>}
            {escHint && <Text dimColor>{skipApprovals || indexStatus?.indexing ? "  ·  " : ""}esc to clear</Text>}
            {queueCount > 0 && (
              <Text color={colors.status.warning}>{escHint || skipApprovals || indexStatus?.indexing ? "  ·  " : ""}{queueCount} queued</Text>
            )}
            {!value && !skipApprovals && !indexStatus?.indexing && !escHint && queueCount === 0 && (
              <Text color={colors.text.disabled}>? for help</Text>
            )}
          </Text>
        </Box>
      )}
      {(showAutocomplete || showHelp) && escHint && (
        <Text dimColor>esc to clear</Text>
      )}

      {showAutocomplete && (
        <AutocompleteList commands={filteredCommands} selectedIndex={selectedIndex} accentValue={accentValue} />
      )}
      {showHelp && <HelpPanel accentValue={accentValue} />}
    </Box>
  );
});
