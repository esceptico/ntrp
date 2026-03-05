import { useState, useMemo, useRef, useCallback } from "react";
import type { TextareaRenderable, KeyEvent } from "@opentui/core";
import type { SlashCommand } from "../types.js";

interface UseAutocompleteOptions {
  value: string;
  commands: readonly SlashCommand[];
  inputRef: React.RefObject<TextareaRenderable | null>;
  setValue: (v: string) => void;
}

export function useAutocomplete({ value, commands, inputRef, setValue }: UseAutocompleteOptions) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filteredCommands = useMemo(() => {
    if (!value.startsWith("/")) return [];
    const query = value.slice(1).toLowerCase();
    if (!query) return commands;
    return commands.filter(
      (cmd) => cmd.name.toLowerCase().startsWith(query) || cmd.name.toLowerCase().includes(query)
    );
  }, [commands, value]);

  const showAutocomplete = value.startsWith("/") && filteredCommands.length > 0;
  const clampedIndex = filteredCommands.length > 0 ? Math.min(selectedIndex, filteredCommands.length - 1) : 0;

  const showAutocompleteRef = useRef(showAutocomplete);
  showAutocompleteRef.current = showAutocomplete;
  const filteredCommandsRef = useRef(filteredCommands);
  filteredCommandsRef.current = filteredCommands;
  const selectedIndexRef = useRef(clampedIndex);
  selectedIndexRef.current = clampedIndex;

  const resetIndex = useCallback(() => setSelectedIndex(0), []);

  const getSelectedCommand = useCallback((): SlashCommand | undefined => {
    if (!showAutocompleteRef.current) return undefined;
    return filteredCommandsRef.current[selectedIndexRef.current];
  }, []);

  const handleAutocompleteKey = useCallback((e: KeyEvent): boolean => {
    if (!showAutocompleteRef.current) return false;

    if (e.name === "up") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(0, i - 1));
      return true;
    }
    if (e.name === "down") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(filteredCommandsRef.current.length - 1, i + 1));
      return true;
    }
    if (e.name === "tab" && filteredCommandsRef.current[selectedIndexRef.current]) {
      e.preventDefault();
      const cmd = filteredCommandsRef.current[selectedIndexRef.current];
      const newText = `/${cmd.name} `;
      const input = inputRef.current;
      if (input) {
        const cursor = input.logicalCursor;
        input.deleteRange(0, 0, cursor.row, cursor.col);
        input.insertText(newText);
        input.cursorOffset = newText.length;
      }
      setValue(newText);
      setSelectedIndex(0);
      return true;
    }
    return false;
  }, [inputRef, setValue]);

  return {
    filteredCommands,
    showAutocomplete,
    selectedIndex: clampedIndex,
    resetIndex,
    getSelectedCommand,
    handleAutocompleteKey,
  };
}
