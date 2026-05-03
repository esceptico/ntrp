import { useState, useCallback, useRef, useMemo, memo, useEffect } from "react";
import type { TextareaRenderable, KeyEvent, PasteEvent } from "@opentui/core";
import type { SlashCommand } from "../../types.js";
import type { ImageBlock } from "../../api/chat.js";
import type { BackgroundTask } from "../../stores/streamingStore.js";
import { colors, useThemeVersion } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { useAutocomplete } from "../../hooks/useAutocomplete.js";
import { AutocompleteList } from "./AutocompleteList.js";
import { InputFooter } from "./InputFooter.js";
import { TRANSCRIPT_GUTTER_WIDTH } from "./messages/TranscriptRow.js";
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
  commands: readonly SlashCommand[];
  messages?: readonly { role: string; content: string; id?: string }[];
  onEditingChange?: (messageId: string | null) => void;
  editing?: boolean;
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
  commands,
  messages = [],
  onEditingChange,
  editing = false,
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
  const [showHelp, setShowHelp] = useState(false);

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
      setShowHelp(false);
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
    setShowHelp(false);
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
    setShowHelp(false);
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

    if (e.name === "escape" && showHelp) {
      e.preventDefault();
      setShowHelp(false);
      return;
    }

    if (e.name === "v" && e.ctrl) {
      if (attachClipboardImage()) {
        e.preventDefault();
        return;
      }
      return;
    }

    if (e.sequence === "?" && !valueRef.current && imagesRef.current.length === 0 && historyIndexRef.current < 0) {
      e.preventDefault();
      setShowHelp((v) => !v);
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
        setShowHelp(false);
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
      setShowHelp(false);
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
  }, [disabled, showHelp, doSubmit, resetInput, handleAutocompleteKey, showAutocomplete, userEntries, notifyEditing]);

  const handleContentChange = useCallback(() => {
    const text = inputRef.current?.plainText ?? "";
    setValue(text);
    resetIndex();
    if (text || imagesRef.current.length > 0) setShowHelp(false);
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
        {showHelp && (
          <box
            flexDirection="column"
            flexShrink={0}
            paddingLeft={TRANSCRIPT_GUTTER_WIDTH}
            paddingBottom={1}
            gap={1}
          >
            <text><span fg={accentValue}>shortcuts</span></text>
            <box flexDirection="row" gap={3}>
              <text><span fg={colors.footer}>enter</span><span fg={colors.text.disabled}> send</span></text>
              <text><span fg={colors.footer}>shift+enter</span><span fg={colors.text.disabled}> newline</span></text>
              <text><span fg={colors.footer}>up</span><span fg={colors.text.disabled}> edit previous</span></text>
              <text><span fg={colors.footer}>esc</span><span fg={colors.text.disabled}> clear/close</span></text>
            </box>
            <box flexDirection="row" gap={3}>
              <text><span fg={colors.footer}>ctrl+n</span><span fg={colors.text.disabled}> new chat</span></text>
              <text><span fg={colors.footer}>ctrl+l</span><span fg={colors.text.disabled}> sidebar</span></text>
              <text><span fg={colors.footer}>ctrl+t</span><span fg={colors.text.disabled}> reasoning</span></text>
              <text><span fg={colors.footer}>shift+tab</span><span fg={colors.text.disabled}> switch chat</span></text>
            </box>
            <box flexDirection="row" gap={3}>
              <text><span fg={colors.footer}>tab tab</span><span fg={colors.text.disabled}> approvals</span></text>
              <text><span fg={colors.footer}>ctrl+o</span><span fg={colors.text.disabled}> background run</span></text>
              <text><span fg={colors.footer}>ctrl+b</span><span fg={colors.text.disabled}> background tasks</span></text>
            </box>
          </box>
        )}
        <box
          border={["top"]}
          borderColor={colors.divider}
          paddingLeft={0}
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
            <box width={TRANSCRIPT_GUTTER_WIDTH} flexShrink={0}>
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
              <box flexDirection="row" flexShrink={0} marginTop={1} justifyContent="space-between">
                <box flexDirection="row" gap={1} overflow="hidden">
                  {editing ? (
                    <text><span fg={colors.status.warning}>editing</span></text>
                  ) : null}
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
                <text>
                  <span fg={colors.footer}>?</span>
                  <span fg={colors.text.disabled}> help</span>
                </text>
              </box>
            </box>
          </box>
        </box>
        <InputFooter
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
