import { useState, useCallback, useRef, useMemo, memo, useEffect } from "react";
import type { TextareaRenderable, KeyEvent } from "@opentui/core";
import type { SlashCommand } from "../../types.js";
import { Status, type Status as StatusType } from "../../lib/constants.js";
import { colors } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { EmptyBorder } from "../ui/border.js";
import { BraillePendulum, BrailleCompress, BrailleSort, CyclingStatus } from "../ui/spinners/index.js";
import { AutocompleteList } from "./AutocompleteList.js";

function formatModel(model?: string): string {
  if (!model) return "";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

interface InputAreaProps {
  onSubmit: (v: string) => void;
  disabled: boolean;
  focus: boolean;
  isStreaming: boolean;
  status: StatusType;
  commands: readonly SlashCommand[];
  queueCount?: number;
  skipApprovals?: boolean;
  chatModel?: string;
  sessionName?: string | null;
  indexStatus?: { indexing: boolean; progress: { total: number; done: number }; reembedding?: boolean; reembed_progress?: { total: number; done: number } | null } | null;
  copiedFlash?: boolean;
}

export const InputArea = memo(function InputArea({
  onSubmit,
  disabled,
  focus,
  isStreaming,
  status,
  commands,
  queueCount = 0,
  skipApprovals = false,
  chatModel,
  sessionName,
  indexStatus = null,
  copiedFlash = false,
}: InputAreaProps) {
  const { accentValue } = useAccentColor();

  const inputRef = useRef<TextareaRenderable>(null);
  const [value, setValue] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [escHint, setEscHint] = useState(false);

  const escPendingRef = useRef(false);
  const escTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    inputRef.current?.clear();
    setValue("");
    setSelectedIndex(0);
    escPendingRef.current = false;
    setEscHint(false);
  }, []);

  // Filtered commands for autocomplete
  const filteredCommands = useMemo(() => {
    if (!value.startsWith("/")) return [];
    const query = value.slice(1).toLowerCase();
    if (!query) return commands;
    return commands.filter(
      (cmd) => cmd.name.toLowerCase().startsWith(query) || cmd.name.toLowerCase().includes(query)
    );
  }, [commands, value]);

  const showAutocomplete = value.startsWith("/") && filteredCommands.length > 0;

  // Keep refs for stable access in callbacks
  const valueRef = useRef(value);
  valueRef.current = value;
  const showAutocompleteRef = useRef(showAutocomplete);
  showAutocompleteRef.current = showAutocomplete;
  const filteredCommandsRef = useRef(filteredCommands);
  filteredCommandsRef.current = filteredCommands;
  const selectedIndexRef = useRef(selectedIndex);
  selectedIndexRef.current = selectedIndex;

  const doSubmit = useCallback(() => {
    if (disabled) return;
    const text = inputRef.current?.plainText ?? "";
    if (!text.trim()) return;

    if (showAutocompleteRef.current && filteredCommandsRef.current[selectedIndexRef.current]) {
      onSubmit(`/${filteredCommandsRef.current[selectedIndexRef.current].name}`);
      resetInput();
      return;
    }

    onSubmit(text);
    resetInput();
  }, [disabled, onSubmit, resetInput]);

  const handleKeyDown = useCallback((e: KeyEvent) => {
    if (disabled) {
      e.preventDefault();
      return;
    }

    // Enter = submit, Shift+Enter = newline (let textarea handle it)
    if (e.name === "return" && !e.shift) {
      e.preventDefault();
      doSubmit();
      return;
    }

    // Autocomplete navigation
    if (showAutocompleteRef.current) {
      if (e.name === "up") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (e.name === "down") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(filteredCommandsRef.current.length - 1, i + 1));
        return;
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
        return;
      }
    }

    // Escape: double-tap to clear
    if (e.name === "escape") {
      if (!valueRef.current) return;
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
  }, [disabled, doSubmit, resetInput]);

  const handleContentChange = useCallback(() => {
    const text = inputRef.current?.plainText ?? "";
    setValue(text);
    setSelectedIndex(0);
  }, []);

  const modelName = formatModel(chatModel);

  return (
    <box flexDirection="column" flexShrink={0}>
      {/* Autocomplete / Help — above input */}
      {showAutocomplete && (
        <AutocompleteList
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          accentValue={accentValue}
        />
      )}

      {/* Prompt container — matches OpenCode's structure exactly */}
      <box>
        {/* Input box with left accent border */}
        <box
          border={["left"]}
          borderColor={accentValue}
          customBorderChars={{
            ...EmptyBorder,
            vertical: "\u2503",
            bottomLeft: "\u2579",
          }}
        >
          <box
            paddingLeft={2}
            paddingRight={2}
            paddingTop={1}
            flexShrink={0}
            backgroundColor={colors.background.element}
            flexGrow={1}
          >
            <textarea
              ref={inputRef as any}
              minHeight={1}
              maxHeight={6}
              placeholder="Message ntrp..."
              focused={focus}
              textColor={colors.text.primary}
              focusedBackgroundColor={colors.background.element}
              keyBindings={[
                { name: "return", shift: true, action: "newline" },
              ]}
              onKeyDown={handleKeyDown}
              onContentChange={handleContentChange}
            />
            <box flexDirection="row" flexShrink={0} paddingTop={1} gap={1}>
              {(sessionName || chatModel) ? (
                <text flexShrink={0} fg={colors.text.muted}>
                  {sessionName ? `${sessionName} · ${modelName}` : modelName}
                </text>
              ) : null}
              {skipApprovals ? (
                <text><span fg={colors.status.warning}><strong>skip approvals</strong></span></text>
              ) : null}
              {queueCount > 0 ? (
                <text><span fg={colors.status.warning}>{queueCount} queued</span></text>
              ) : null}
            </box>
          </box>
        </box>
        {/* Bottom cap — half-block transition */}
        <box
          height={1}
          border={["left"]}
          borderColor={accentValue}
          customBorderChars={{ ...EmptyBorder, vertical: "\u2579" }}
        >
          <box
            height={1}
            border={["bottom"]}
            borderColor={colors.background.element}
            customBorderChars={{ ...EmptyBorder, horizontal: "\u2580" }}
          />
        </box>
        {/* Footer */}
        <box flexDirection="row" justifyContent="space-between">
          {isStreaming || status === Status.COMPRESSING ? (
            <>
              <box flexDirection="row" gap={1} flexGrow={1}>
                <box marginLeft={3}>
                  {status === Status.COMPRESSING ? (
                    <BrailleCompress width={8} color={accentValue} interval={30} />
                  ) : (
                    <BraillePendulum width={8} color={accentValue} spread={1} interval={20} />
                  )}
                </box>
                {status === Status.COMPRESSING ? (
                  <text><span fg={colors.text.muted}>compressing context</span></text>
                ) : (
                  <CyclingStatus status={status} isStreaming={isStreaming} />
                )}
              </box>
              {isStreaming && (
                <text>
                  <span fg={colors.footer}>esc</span>
                  <span fg={colors.text.disabled}> interrupt</span>
                </text>
              )}
            </>
          ) : (
            <>
              <box flexDirection="row" marginLeft={3}>
                {indexStatus?.indexing || indexStatus?.reembedding ? (
                  <box flexDirection="row" gap={1}>
                    <BrailleSort width={8} color={accentValue} interval={40} />
                    <text><span fg={colors.text.muted}>{indexStatus.reembedding ? "re-embedding" : "indexing"}</span></text>
                  </box>
                ) : null}
                <text>
                  {copiedFlash ? (
                    <span fg={colors.text.muted}>Copied to clipboard</span>
                  ) : escHint ? (
                    <span fg={accentValue}>esc again to clear</span>
                  ) : null}
                </text>
              </box>
              <box gap={2} flexDirection="row">
                <text>
                  <span fg={colors.footer}>ctrl+n</span>
                  <span fg={colors.text.disabled}> new chat</span>
                </text>
                <text>
                  <span fg={colors.footer}>ctrl+l</span>
                  <span fg={colors.text.disabled}> side panel</span>
                </text>
                <text>
                  <span fg={colors.footer}>shift+tab</span>
                  <span fg={colors.text.disabled}> approvals</span>
                </text>
              </box>
            </>
          )}
        </box>
      </box>
    </box>
  );
});
