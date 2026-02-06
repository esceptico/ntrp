import React, { useState, useCallback } from "react";
import { Box, Text } from "ink";
import { colors } from "../ui/colors.js";
import { useDimensions } from "../../contexts/index.js";
import { truncateText, SelectionIndicator, TextInputField } from "../ui/index.js";
import { useKeypress, useInlineTextInput, useAccentColor, type Key } from "../../hooks/index.js";
import type { ChoiceOption } from "../../types.js";

interface ChoiceSelectorProps {
  question: string;
  options: ChoiceOption[];
  allowMultiple: boolean;
  onSelect: (selected: string[]) => void;
  onCancel: () => void;
  isActive?: boolean;
}

export function ChoiceSelector({
  question,
  options,
  allowMultiple,
  onSelect,
  onCancel,
  isActive = true,
}: ChoiceSelectorProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const totalOptions = options.length + 1;
  const otherIndex = options.length;

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const textInput = useInlineTextInput();

  const contentWidth = Math.max(0, terminalWidth - 8);
  const labelWidth = Math.max(0, contentWidth - 15);
  const isOnOther = selectedIndex === otherIndex;

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        if (isOnOther && textInput.value) {
          textInput.reset();
          return;
        }
        onCancel();
        return;
      }
      if (key.ctrl && key.name === "c") {
        onCancel();
        return;
      }

      if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(totalOptions - 1, i + 1));
        return;
      }

      if (isOnOther) {
        if (key.name === "return") {
          if (textInput.value.trim()) {
            onSelect([textInput.value.trim()]);
          }
          return;
        }
        if (textInput.handleKey(key)) return;
        return;
      }

      if (key.sequence && /^[1-9]$/.test(key.sequence)) {
        const num = parseInt(key.sequence, 10) - 1;
        if (num < options.length) {
          if (allowMultiple) {
            setSelectedIndex(num);
            setChecked((prev) => {
              const next = new Set(prev);
              const id = options[num].id;
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            });
          } else {
            onSelect([options[num].id]);
          }
        }
        return;
      }

      if (key.name === "space" && allowMultiple && !isOnOther) {
        const id = options[selectedIndex].id;
        setChecked((prev) => {
          const next = new Set(prev);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        });
        return;
      }

      if (key.name === "return") {
        if (allowMultiple) {
          const result = checked.size > 0
            ? Array.from(checked)
            : [options[selectedIndex].id];
          onSelect(result);
        } else {
          onSelect([options[selectedIndex].id]);
        }
        return;
      }
    },
    [options, selectedIndex, allowMultiple, checked, isOnOther, textInput, totalOptions, onSelect, onCancel]
  );

  useKeypress(handleKeypress, { isActive });

  const hintText = isOnOther
    ? textInput.value
      ? "Enter to submit · Esc to clear"
      : "Type your answer · Esc to cancel"
    : allowMultiple
      ? "↑↓ navigate · Space toggle · Enter submit · Esc cancel"
      : "↑↓ navigate · Enter select · Esc cancel";

  return (
    <Box flexDirection="column" marginY={1} width={terminalWidth - 2} overflow="hidden">
      <Text color={colors.text.primary} bold>
        {" "}{truncateText(question, contentWidth)}
      </Text>
      <Box height={1} />

      <Box flexDirection="column" marginLeft={2} width={contentWidth} overflow="hidden">
        {options.map((opt, i) => {
          const isSelected = i === selectedIndex;
          const isChecked = checked.has(opt.id);

          return (
            <Text key={opt.id}>
              <SelectionIndicator selected={isSelected} accent={accentValue} />
              {allowMultiple && (
                <Text color={isChecked ? accentValue : colors.text.disabled}>
                  {isChecked ? "◉ " : "○ "}
                </Text>
              )}
              <Text color={colors.text.disabled}>{i + 1}. </Text>
              <Text color={isSelected ? colors.text.primary : colors.text.secondary}>
                {truncateText(opt.label, labelWidth)}
              </Text>
              {opt.description && (
                <Text color={colors.text.muted}> — {truncateText(opt.description, labelWidth - opt.label.length - 3)}</Text>
              )}
            </Text>
          );
        })}

        <Text>
          <SelectionIndicator selected={isOnOther} accent={accentValue} />
          {allowMultiple && (
            <Text color={colors.text.disabled}>{"○ "}</Text>
          )}
          <Text color={colors.text.disabled}>{options.length + 1}. </Text>
          <TextInputField
            value={textInput.value}
            cursorPos={textInput.cursorPos}
            placeholder="Other (type your answer)"
            showCursor={isOnOther}
            placeholderColor={isOnOther ? colors.text.secondary : colors.text.muted}
          />
        </Text>
      </Box>

      <Box height={1} />

      <Text color={colors.text.disabled}> {hintText}</Text>
    </Box>
  );
}
