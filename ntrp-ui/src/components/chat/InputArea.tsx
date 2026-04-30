import { useState, useCallback, useRef, useMemo, memo, useEffect } from "react";
import type { TextareaRenderable, KeyEvent, PasteEvent } from "@opentui/core";
import type { SlashCommand } from "../../types.js";
import type { Status as StatusType } from "../../lib/constants.js";
import type { ImageBlock } from "../../api/chat.js";
import type { BackgroundTask } from "../../stores/streamingStore.js";
import { colors, useThemeVersion } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { useAutocomplete } from "../../hooks/useAutocomplete.js";
import { AutocompleteList } from "./AutocompleteList.js";
import { InputFooter } from "./InputFooter.js";
import { getClipboardImage } from "../../lib/clipboard.js";
import { getImagePixels } from "../../lib/image-preview.js";

function formatModel(model?: string): string {
  if (!model) return "";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

interface InputAreaProps {
  onSubmit: (v: string, images?: ImageBlock[]) => void;
  onEditSubmit?: (message: string, turns: number) => void;
  disabled: boolean;
  focus: boolean;
  isStreaming: boolean;
  status: StatusType;
  commands: readonly SlashCommand[];
  messages?: readonly { role: string; content: string; id?: string }[];
  onEditingChange?: (messageId: string | null) => void;
  skipApprovals?: boolean;
  chatModel?: string;
  reasoningEffort?: string | null;
  indexStatus?: { indexing: boolean; progress: { total: number; done: number }; reembedding?: boolean; reembed_progress?: { total: number; done: number } | null } | null;
  copiedFlash?: boolean;
  backgroundTaskCount?: number;
  backgroundTasks?: Map<string, BackgroundTask>;
  onCancelBackgroundTask?: (taskId: string) => void;
  prefill?: string | null;
  onPrefillConsumed?: () => void;
}

export const InputArea = memo(function InputArea({
  onSubmit,
  onEditSubmit,
  disabled,
  focus,
  isStreaming,
  status,
  commands,
  messages = [],
  onEditingChange,
  skipApprovals = false,
  chatModel,
  reasoningEffort = null,
  indexStatus = null,
  copiedFlash = false,
  backgroundTaskCount = 0,
  backgroundTasks,
  onCancelBackgroundTask,
  prefill = null,
  onPrefillConsumed,
}: InputAreaProps) {
  const { accentValue } = useAccentColor();

  useThemeVersion();
  const inputRef = useRef<TextareaRenderable | null>(null);
  const [value, setValue] = useState("");
  const [escHint, setEscHint] = useState(false);
  const [images, setImages] = useState<ImageBlock[]>([]);

  const escPendingRef = useRef(false);
  const escTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const userEntries = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => ({ content: m.content, id: m.id })),
    [messages]
  );
  const historyIndexRef = useRef(-1);
  const historyNavRef = useRef(false);

  const notifyEditing = useCallback((idx: number) => {
    if (!onEditingChange) return;
    if (idx < 0) {
      onEditingChange(null);
    } else {
      const entry = userEntries[userEntries.length - 1 - idx];
      onEditingChange(entry?.id ?? null);
    }
  }, [onEditingChange, userEntries]);

  useEffect(() => {
    return () => {
      if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (prefill != null && inputRef.current) {
      inputRef.current.setText(prefill);
      inputRef.current.editBuffer.setCursorByOffset(prefill.length);
      setValue(prefill);
      onPrefillConsumed?.();
    }
  }, [prefill, onPrefillConsumed]);

  const {
    filteredCommands,
    showAutocomplete,
    selectedIndex,
    resetIndex,
    getSelectedCommand,
    handleAutocompleteKey,
    selectByIndex,
  } = useAutocomplete({ value, commands, inputRef, setValue });

  const resetInput = useCallback(() => {
    if (escTimeoutRef.current) {
      clearTimeout(escTimeoutRef.current);
      escTimeoutRef.current = null;
    }
    inputRef.current?.clear();
    setValue("");
    setImages([]);
    resetIndex();
    escPendingRef.current = false;
    setEscHint(false);
  }, [resetIndex]);

  const valueRef = useRef(value);
  valueRef.current = value;

  const imagesRef = useRef(images);
  imagesRef.current = images;

  const doSubmit = useCallback(() => {
    if (disabled) return;
    const text = inputRef.current?.plainText ?? "";
    if (!text.trim() && imagesRef.current.length === 0) return;

    const pendingImages = imagesRef.current.length > 0 ? imagesRef.current : undefined;

    const selected = getSelectedCommand();
    if (selected) {
      onSubmit(`/${selected.name}`, pendingImages);
      resetInput();
      historyIndexRef.current = -1;
      notifyEditing(-1);
      return;
    }

    const histIdx = historyIndexRef.current;
    if (histIdx >= 0 && onEditSubmit) {
      const turns = histIdx + 1;
      onEditSubmit(text, turns);
      resetInput();
      historyIndexRef.current = -1;
      notifyEditing(-1);
      return;
    }

    onSubmit(text, pendingImages);
    resetInput();
    historyIndexRef.current = -1;
    notifyEditing(-1);
  }, [disabled, onSubmit, onEditSubmit, resetInput, getSelectedCommand, notifyEditing]);

  const attachClipboardImage = useCallback(() => {
    const img = getClipboardImage();
    if (!img) return false;
    setImages((prev) => [...prev, img]);
    return true;
  }, []);

  const handlePaste = useCallback((e: PasteEvent) => {
    if (attachClipboardImage()) e.preventDefault();
  }, [attachClipboardImage]);

  const handleKeyDown = useCallback((e: KeyEvent) => {
    if (disabled) {
      e.preventDefault();
      return;
    }

    if (e.name === "v" && e.ctrl) {
      if (attachClipboardImage()) {
        e.preventDefault();
        return;
      }
      return;
    }

    if (e.name === "return" && !e.shift) {
      e.preventDefault();
      doSubmit();
      return;
    }

    if (handleAutocompleteKey(e)) return;

    if (e.name === "up" && !showAutocomplete && (!valueRef.current || historyIndexRef.current >= 0)) {
      e.preventDefault();
      const nextIdx = historyIndexRef.current + 1;
      if (nextIdx < userEntries.length) {
        historyIndexRef.current = nextIdx;
        historyNavRef.current = true;
        const entry = userEntries[userEntries.length - 1 - nextIdx];
        inputRef.current?.setText(entry.content);
        inputRef.current?.editBuffer.setCursorByOffset(entry.content.length);
        setValue(entry.content);
        notifyEditing(nextIdx);
      }
      return;
    }

    if (e.name === "down" && !showAutocomplete && historyIndexRef.current >= 0) {
      e.preventDefault();
      historyNavRef.current = true;
      const nextIdx = historyIndexRef.current - 1;
      historyIndexRef.current = nextIdx;
      if (nextIdx < 0) {
        inputRef.current?.clear();
        setValue("");
      } else {
        const entry = userEntries[userEntries.length - 1 - nextIdx];
        inputRef.current?.setText(entry.content);
        inputRef.current?.editBuffer.setCursorByOffset(entry.content.length);
        setValue(entry.content);
      }
      notifyEditing(nextIdx);
      return;
    }

    if (e.name === "escape") {
      if (imagesRef.current.length > 0) {
        setImages((prev) => prev.slice(0, -1));
        return;
      }
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
  }, [disabled, doSubmit, resetInput, handleAutocompleteKey, showAutocomplete, userEntries, notifyEditing]);

  const handleContentChange = useCallback(() => {
    const text = inputRef.current?.plainText ?? "";
    setValue(text);
    resetIndex();
    if (historyNavRef.current) {
      historyNavRef.current = false;
      return;
    }
    if (historyIndexRef.current >= 0) {
      historyIndexRef.current = -1;
      notifyEditing(-1);
    }
  }, [resetIndex, notifyEditing]);

  const modelName = formatModel(chatModel);
  const metadata = [
    modelName || null,
    reasoningEffort ? `think ${reasoningEffort}` : null,
  ].filter(Boolean).join(" · ");
  const imagePreview = useMemo(() => {
    if (images.length === 0) return null;
    const last = images[images.length - 1];
    return getImagePixels(last.data, last.media_type);
  }, [images]);

  return (
    <box flexDirection="column" flexShrink={0}>
      {showAutocomplete && (
        <AutocompleteList
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          accentValue={accentValue}
          onItemClick={selectByIndex}
        />
      )}

      <box flexDirection="column">
        <box
          border={["top"]}
          borderColor={colors.divider}
          paddingLeft={2}
          paddingRight={2}
          paddingTop={1}
          paddingBottom={1}
          flexShrink={0}
        >
          <box
            flexDirection="row"
            flexGrow={1}
            overflow="hidden"
          >
            <box width={4} flexShrink={0}>
              <text><span fg={accentValue}>›</span></text>
            </box>
            <box flexDirection="column" flexGrow={1} overflow="hidden">
              {imagePreview && (
                <box flexDirection="column" flexShrink={0} paddingBottom={1}>
                  {imagePreview.map((row, y) => (
                    <text key={y}>
                      {row.pixels.map((p, x) => (
                        <span key={x} fg={p.fg} bg={p.bg}>▀</span>
                      ))}
                    </text>
                  ))}
                </box>
              )}
              <textarea
                ref={inputRef}
                minHeight={1}
                maxHeight={6}
                placeholder={images.length > 0 ? `${images.length} image${images.length > 1 ? "s" : ""} attached · type a message or press Enter` : "Message ntrp..."}
                focused={focus}
                textColor={colors.text.primary}
                placeholderColor={colors.text.disabled}
                focusedBackgroundColor={colors.background.base}
                keyBindings={[
                  { name: "return", shift: true, action: "newline" },
                ]}
                onPaste={handlePaste}
                onKeyDown={handleKeyDown}
                onContentChange={handleContentChange}
              />
              <box flexDirection="row" flexShrink={0} marginTop={1} gap={1}>
                {images.length > 0 ? (
                  <text><span fg={accentValue}>{images.length} image{images.length > 1 ? "s" : ""} · esc to remove</span></text>
                ) : null}
                {metadata ? (
                  <text flexShrink={0} fg={colors.text.muted}>
                    {metadata}
                  </text>
                ) : null}
                {skipApprovals ? (
                  <text><span fg={colors.status.warning}><strong>skip approvals</strong></span></text>
                ) : null}
              </box>
            </box>
          </box>
        </box>
        <InputFooter
          isStreaming={isStreaming}
          status={status}
          accentValue={accentValue}
          escHint={escHint}
          copiedFlash={copiedFlash}
          backgroundTaskCount={backgroundTaskCount}
          backgroundTasks={backgroundTasks}
          onCancelBackgroundTask={onCancelBackgroundTask}
          indexStatus={indexStatus}
        />
      </box>
    </box>
  );
});
