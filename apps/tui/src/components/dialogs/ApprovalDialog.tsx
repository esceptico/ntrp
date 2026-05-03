import { useState, useMemo, useCallback } from "react";
import { colors } from "../ui/colors.js";
import { useDimensions } from "../../contexts/index.js";
import { truncateText, SelectionIndicator, BaseSelectionList } from "../ui/index.js";
import { useKeypress, useAccentColor, type Key } from "../../hooks/index.js";
import type { PendingApproval, ApprovalResult } from "../../types.js";
import { DiffView } from "./DiffView.js";

const ALWAYS_TEXT = "Yes, and don't ask again for this session";

interface ApprovalDialogProps {
  approval: PendingApproval;
  onResult: (result: ApprovalResult, feedback?: string) => void;
  isActive?: boolean;
}

export function ApprovalDialog({ approval, onResult, isActive = true }: ApprovalDialogProps) {
  const { width: terminalWidth } = useDimensions();
  const { accentValue } = useAccentColor();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [customReason, setCustomReason] = useState("");

  const contentWidth = Math.max(0, terminalWidth - 4);
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
          onResult("reject", customReason.trim() || undefined);
          return;
        }
        if (key.name === "escape") {
          if (customReason) {
            setCustomReason("");
          } else {
            onResult("reject");
          }
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
    [isOnCustomOption, customReason, selectedIndex, onResult]
  );

  useKeypress(handleKeypress, { isActive });

  const hasDiff = approval.diff && approval.diff.length > 0;

  const memoizedContent = useMemo(() => {
    return (
      <>
        {approval.path && <text><span fg={colors.text.primary}>{truncateText(approval.path, contentWidth)}</span></text>}
        {hasDiff && <DiffView diff={approval.diff!} width={contentWidth} />}
        {!hasDiff && approval.preview && <text><span fg={colors.text.secondary}>{truncateText(approval.preview, contentWidth)}</span></text>}
      </>
    );
  }, [approval.preview, approval.path, approval.diff, hasDiff, contentWidth]);

  const alwaysTextTruncated = truncateText(ALWAYS_TEXT, contentWidth - 5);
  const options: Array<{ id: "once" | "always" | "custom"; label: string }> = [
    { id: "once", label: "1. Yes" },
    { id: "always", label: `2. ${alwaysTextTruncated}` },
    { id: "custom", label: "3. No, and tell ntrp what to do differently" },
  ];

  return (
    <box
      flexDirection="column"
      marginY={1}
      width={terminalWidth}
      overflow="hidden"
      border={["left"]}
      borderStyle="heavy"
      borderColor={accentValue}
      paddingLeft={1}
    >
      <text><span fg={colors.text.primary}><strong>{header}</strong></span></text>

      <box flexDirection="column" marginTop={1} width={contentWidth} overflow="hidden">
        {memoizedContent}
      </box>

      <box flexDirection="column" marginTop={1}>
        <BaseSelectionList
          items={options}
          selectedIndex={selectedIndex}
          visibleLines={3}
          showIndicator={false}
          onItemClick={(index, item) => {
            setSelectedIndex(index);
            if (item.id === "once") onResult("once");
            else if (item.id === "always") onResult("always");
          }}
          renderItem={(item, ctx) => (
            <text>
              <SelectionIndicator selected={ctx.isSelected} accent={accentValue} />
              <span fg={ctx.isSelected ? colors.text.primary : colors.text.secondary}>{item.label}</span>
            </text>
          )}
        />
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>Reason:</span></text>
          <input
            value={customReason}
            onInput={setCustomReason}
            placeholder={customPlaceholder}
            focused={isOnCustomOption}
            textColor={colors.text.primary}
            focusedTextColor={colors.text.primary}
            cursorColor={accentValue}
            placeholderColor={colors.text.muted}
            width={Math.max(8, contentWidth)}
          />
        </box>
      </box>

      <box marginTop={1}>
        <text><span fg={colors.text.disabled}>{hintText}</span></text>
      </box>
    </box>
  );
}
