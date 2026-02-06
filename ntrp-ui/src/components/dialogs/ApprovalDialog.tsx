import React, { useState, useMemo, useCallback } from "react";
import { Box, Text } from "ink";
import { colors } from "../ui/colors.js";
import { useDimensions } from "../../contexts/index.js";
import { truncateText, SelectionIndicator, TextInputField } from "../ui/index.js";
import { useKeypress, useInlineTextInput, useAccentColor, type Key } from "../../hooks/index.js";
import type { PendingApproval, ApprovalResult } from "../../types.js";
import { DiffView } from "./DiffView.js";

export type { PendingApproval, ApprovalResult } from "../../types.js";

const ALWAYS_TEXT = "Yes, and don't ask again for this project";

interface ApprovalDialogProps {
  approval: PendingApproval;
  onResult: (result: ApprovalResult, feedback?: string) => void;
  isActive?: boolean;
}

export function ApprovalDialog({ approval, onResult, isActive = true }: ApprovalDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const textInput = useInlineTextInput();

  const contentWidth = Math.max(0, terminalWidth - 8);
  const header = `Allow ${approval.name.replace(/_/g, " ")}?`;

  const isOnCustomOption = selectedIndex === 2;
  const customPlaceholder = "No, and tell ntrp what to do differently";

  const hintText = isOnCustomOption
    ? textInput.value
      ? "Enter to submit · Esc to clear"
      : "Type reason · Esc to cancel"
    : "Enter to select · Esc to cancel";

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.ctrl && key.name === "c") {
        onResult("reject");
        return;
      }

      if (key.name === "up") {
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down") {
        setSelectedIndex((i) => Math.min(2, i + 1));
        return;
      }

      if (!isOnCustomOption && key.sequence === "y") {
        onResult("once");
        return;
      }
      if (!isOnCustomOption && key.sequence === "n") {
        onResult("reject");
        return;
      }

      if (isOnCustomOption) {
        if (key.name === "return") {
          onResult("reject", textInput.value.trim() || undefined);
          return;
        }
        if (key.name === "escape") {
          if (textInput.value) {
            textInput.reset();
          } else {
            onResult("reject");
          }
          return;
        }
        if (textInput.handleKey(key)) return;
      }

      if (key.name === "return") {
        if (selectedIndex === 0) {
          onResult("once");
        } else if (selectedIndex === 1) {
          onResult("always");
        }
        return;
      }
      if (key.name === "escape") {
        onResult("reject");
      }
    },
    [isOnCustomOption, textInput, selectedIndex, onResult]
  );

  useKeypress(handleKeypress, { isActive });

  const hasDiff = approval.diff && approval.diff.length > 0;

  const memoizedContent = useMemo(() => {
    return (
      <>
        {approval.path && <Text color={colors.text.primary}>{truncateText(approval.path, contentWidth)}</Text>}
        {hasDiff && <DiffView diff={approval.diff!} width={contentWidth} />}
        {!hasDiff && approval.preview && <Text color={colors.text.secondary}>{truncateText(approval.preview, contentWidth)}</Text>}
      </>
    );
  }, [approval.preview, approval.path, approval.diff, hasDiff, contentWidth]);

  const alwaysTextTruncated = truncateText(ALWAYS_TEXT, contentWidth - 5);

  return (
    <Box flexDirection="column" marginY={1} width={terminalWidth - 2} overflow="hidden">
      <Text color={colors.text.primary} bold> {header}</Text>
      <Box height={1} />

      <Box flexDirection="column" marginLeft={3} width={contentWidth} overflow="hidden">
        {memoizedContent}
      </Box>

      <Box height={1} />

      <Box flexDirection="column" marginLeft={3}>
        <Text>
          <SelectionIndicator selected={selectedIndex === 0} accent={accentValue} />
          <Text color={selectedIndex === 0 ? colors.text.primary : colors.text.secondary}>
            1. Yes
          </Text>
        </Text>

        <Text>
          <SelectionIndicator selected={selectedIndex === 1} accent={accentValue} />
          <Text color={selectedIndex === 1 ? colors.text.primary : colors.text.secondary}>
            2. {alwaysTextTruncated}
          </Text>
        </Text>

        <Text>
          <SelectionIndicator selected={isOnCustomOption} accent={accentValue} />
          <Text color={isOnCustomOption ? colors.text.primary : colors.text.secondary}>
            3.{" "}
          </Text>
          <TextInputField
            value={textInput.value}
            cursorPos={textInput.cursorPos}
            placeholder={customPlaceholder}
            showCursor={isOnCustomOption}
          />
        </Text>
      </Box>

      <Box height={1} />

      <Text color={colors.text.disabled}> {hintText}</Text>
    </Box>
  );
}
