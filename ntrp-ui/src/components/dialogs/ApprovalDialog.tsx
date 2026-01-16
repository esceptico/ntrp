import React, { useState, useMemo, useCallback } from "react";
import { Box, Text } from "ink";
import { brand, colors } from "../ui/colors.js";
import { useDimensions } from "../../contexts/index.js";
import { truncateText } from "../ui/index.js";
import { useKeypress, type Key } from "../../hooks/index.js";
import type { PendingApproval, ApprovalResult } from "../../types.js";
import { DiffView } from "./DiffView.js";

export type { PendingApproval, ApprovalResult } from "../../types.js";

const ALWAYS_TEXT = "Yes, and don't ask again for this project";

interface ApprovalDialogProps {
  approval: PendingApproval;
  onResult: (result: ApprovalResult, feedback?: string) => void;
}

export function ApprovalDialog({ approval, onResult }: ApprovalDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const [selectedIndex, setSelectedIndex] = useState(2);
  const [customReason, setCustomReason] = useState("");
  const [cursorPos, setCursorPos] = useState(0);

  const contentWidth = Math.max(0, terminalWidth - 8);
  const header = `Allow ${approval.name.replace(/_/g, " ")}?`;

  const isOnCustomOption = selectedIndex === 2;
  const customPlaceholder = "No, and tell ntrp what to do differently";

  const hintText = isOnCustomOption
    ? customReason
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

      if (isOnCustomOption) {
        if (key.name === "return") {
          onResult("reject", customReason.trim() || undefined);
          return;
        }
        if (key.name === "escape") {
          if (customReason) {
            setCustomReason("");
            setCursorPos(0);
          } else {
            onResult("reject");
          }
          return;
        }
        if (key.name === "left") {
          setCursorPos((p) => Math.max(0, p - 1));
          return;
        }
        if (key.name === "right") {
          setCursorPos((p) => Math.min(customReason.length, p + 1));
          return;
        }
        if (key.name === "backspace" || key.name === "delete") {
          if (cursorPos > 0) {
            setCustomReason((t) => t.slice(0, cursorPos - 1) + t.slice(cursorPos));
            setCursorPos((p) => p - 1);
          }
          return;
        }
        if (key.insertable && key.sequence && !key.ctrl && !key.meta) {
          setCustomReason((t) => t.slice(0, cursorPos) + key.sequence + t.slice(cursorPos));
          setCursorPos((p) => p + key.sequence.length);
          return;
        }
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
    [isOnCustomOption, customReason, cursorPos, selectedIndex, onResult]
  );

  useKeypress(handleKeypress, { isActive: true });

  const hasDiff = approval.diff && approval.diff.length > 0;

  const memoizedContent = useMemo(() => {
    return (
      <>
        {approval.path && <Text color={colors.text.primary}>{truncateText(approval.path, contentWidth)}</Text>}
        {approval.preview && <Text color={colors.text.secondary}>{truncateText(approval.preview, contentWidth)}</Text>}
        {hasDiff && <DiffView diff={approval.diff!} width={contentWidth} />}
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
          <Text color={selectedIndex === 0 ? brand.primary : colors.text.disabled}>
            {selectedIndex === 0 ? "❯ " : "  "}
          </Text>
          <Text color={selectedIndex === 0 ? colors.text.primary : colors.text.secondary}>
            1. Yes
          </Text>
        </Text>

        <Text>
          <Text color={selectedIndex === 1 ? brand.primary : colors.text.disabled}>
            {selectedIndex === 1 ? "❯ " : "  "}
          </Text>
          <Text color={selectedIndex === 1 ? colors.text.primary : colors.text.secondary}>
            2. {alwaysTextTruncated}
          </Text>
        </Text>

        <Text>
          <Text color={isOnCustomOption ? brand.primary : colors.text.disabled}>
            {isOnCustomOption ? "❯ " : "  "}
          </Text>
          <Text color={isOnCustomOption ? colors.text.primary : colors.text.secondary}>
            3.{" "}
          </Text>
          {customReason ? (
            <Text>
              {customReason.slice(0, cursorPos)}
              {isOnCustomOption && "█"}
              {customReason.slice(cursorPos)}
            </Text>
          ) : (
            <Text color={colors.text.muted}>
              {customPlaceholder}
              {isOnCustomOption && "█"}
            </Text>
          )}
        </Text>
      </Box>

      <Box height={1} />

      <Text color={colors.text.disabled}> {hintText}</Text>
    </Box>
  );
}
