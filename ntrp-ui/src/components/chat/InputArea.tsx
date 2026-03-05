import { useState, useCallback, useRef, memo, useEffect } from "react";
import type { TextareaRenderable, KeyEvent } from "@opentui/core";
import type { SlashCommand } from "../../types.js";
import type { Status as StatusType } from "../../lib/constants.js";
import { colors } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { useAutocomplete } from "../../hooks/useAutocomplete.js";
import { EmptyBorder } from "../ui/border.js";
import { AutocompleteList } from "./AutocompleteList.js";
import { InputFooter } from "./InputFooter.js";

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
  const [escHint, setEscHint] = useState(false);

  const escPendingRef = useRef(false);
  const escTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
    };
  }, []);

  const {
    filteredCommands,
    showAutocomplete,
    selectedIndex,
    resetIndex,
    getSelectedCommand,
    handleAutocompleteKey,
  } = useAutocomplete({ value, commands, inputRef, setValue });

  const resetInput = useCallback(() => {
    if (escTimeoutRef.current) {
      clearTimeout(escTimeoutRef.current);
      escTimeoutRef.current = null;
    }
    inputRef.current?.clear();
    setValue("");
    resetIndex();
    escPendingRef.current = false;
    setEscHint(false);
  }, [resetIndex]);

  const valueRef = useRef(value);
  valueRef.current = value;

  const doSubmit = useCallback(() => {
    if (disabled) return;
    const text = inputRef.current?.plainText ?? "";
    if (!text.trim()) return;

    const selected = getSelectedCommand();
    if (selected) {
      onSubmit(`/${selected.name}`);
      resetInput();
      return;
    }

    onSubmit(text);
    resetInput();
  }, [disabled, onSubmit, resetInput, getSelectedCommand]);

  const handleKeyDown = useCallback((e: KeyEvent) => {
    if (disabled) {
      e.preventDefault();
      return;
    }

    if (e.name === "return" && !e.shift) {
      e.preventDefault();
      doSubmit();
      return;
    }

    if (handleAutocompleteKey(e)) return;

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
  }, [disabled, doSubmit, resetInput, handleAutocompleteKey]);

  const handleContentChange = useCallback(() => {
    const text = inputRef.current?.plainText ?? "";
    setValue(text);
    resetIndex();
  }, [resetIndex]);

  const modelName = formatModel(chatModel);

  return (
    <box flexDirection="column" flexShrink={0}>
      {showAutocomplete && (
        <AutocompleteList
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          accentValue={accentValue}
        />
      )}

      <box>
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
        <InputFooter
          isStreaming={isStreaming}
          status={status}
          accentValue={accentValue}
          escHint={escHint}
          copiedFlash={copiedFlash}
          indexStatus={indexStatus}
        />
      </box>
    </box>
  );
});
