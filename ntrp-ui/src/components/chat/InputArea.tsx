import { useState, useCallback, useRef, useMemo, memo, useEffect } from "react";
import type { TextareaRenderable, KeyEvent, PasteEvent } from "@opentui/core";
import type { SlashCommand } from "../../types.js";
import type { Status as StatusType } from "../../lib/constants.js";
import type { ImageBlock } from "../../api/chat.js";
import { colors } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { useAutocomplete } from "../../hooks/useAutocomplete.js";
import { EmptyBorder } from "../ui/border.js";
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
  messages?: readonly { role: string; content: string }[];
  queueCount?: number;
  skipApprovals?: boolean;
  chatModel?: string;
  sessionName?: string | null;
  indexStatus?: { indexing: boolean; progress: { total: number; done: number }; reembedding?: boolean; reembed_progress?: { total: number; done: number } | null } | null;
  copiedFlash?: boolean;
  backgroundTaskCount?: number;
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
  queueCount = 0,
  skipApprovals = false,
  chatModel,
  sessionName,
  indexStatus = null,
  copiedFlash = false,
  backgroundTaskCount = 0,
  prefill = null,
  onPrefillConsumed,
}: InputAreaProps) {
  const { accentValue } = useAccentColor();

  const inputRef = useRef<TextareaRenderable>(null);
  const [value, setValue] = useState("");
  const [escHint, setEscHint] = useState(false);
  const [images, setImages] = useState<ImageBlock[]>([]);

  const escPendingRef = useRef(false);
  const escTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const userMessages = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => m.content),
    [messages]
  );
  const historyIndexRef = useRef(-1);
  const historyNavRef = useRef(false);

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
      return;
    }

    const histIdx = historyIndexRef.current;
    if (histIdx >= 0 && onEditSubmit) {
      const turns = histIdx + 1;
      onEditSubmit(text, turns);
      resetInput();
      historyIndexRef.current = -1;
      return;
    }

    onSubmit(text, pendingImages);
    resetInput();
    historyIndexRef.current = -1;
  }, [disabled, onSubmit, onEditSubmit, resetInput, getSelectedCommand]);

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
      if (nextIdx < userMessages.length) {
        historyIndexRef.current = nextIdx;
        historyNavRef.current = true;
        const msg = userMessages[userMessages.length - 1 - nextIdx];
        inputRef.current?.setText(msg);
        inputRef.current?.editBuffer.setCursorByOffset(msg.length);
        setValue(msg);
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
        const msg = userMessages[userMessages.length - 1 - nextIdx];
        inputRef.current?.setText(msg);
        inputRef.current?.editBuffer.setCursorByOffset(msg.length);
        setValue(msg);
      }
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
  }, [disabled, doSubmit, resetInput, handleAutocompleteKey, showAutocomplete, userMessages]);

  const handleContentChange = useCallback(() => {
    const text = inputRef.current?.plainText ?? "";
    setValue(text);
    resetIndex();
    if (historyNavRef.current) {
      historyNavRef.current = false;
    } else {
      historyIndexRef.current = -1;
    }
  }, [resetIndex]);

  const modelName = formatModel(chatModel);
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
              ref={inputRef as any}
              minHeight={1}
              maxHeight={6}
              placeholder={images.length > 0 ? `${images.length} image${images.length > 1 ? "s" : ""} attached · type a message or press Enter` : "Message ntrp..."}
              focused={focus}
              textColor={colors.text.primary}
              focusedBackgroundColor={colors.background.element}
              keyBindings={[
                { name: "return", shift: true, action: "newline" },
              ]}
              onPaste={handlePaste}
              onKeyDown={handleKeyDown}
              onContentChange={handleContentChange}
            />
            <box flexDirection="row" flexShrink={0} paddingTop={1} gap={1}>
              {images.length > 0 ? (
                <text><span fg={accentValue}>{images.length} image{images.length > 1 ? "s" : ""} · esc to remove</span></text>
              ) : null}
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
          {colors.background.element != null && (
            <box
              height={1}
              border={["bottom"]}
              borderColor={colors.background.element}
              customBorderChars={{ ...EmptyBorder, horizontal: "\u2580" }}
            />
          )}
        </box>
        <InputFooter
          isStreaming={isStreaming}
          status={status}
          accentValue={accentValue}
          escHint={escHint}
          copiedFlash={copiedFlash}
          backgroundTaskCount={backgroundTaskCount}
          indexStatus={indexStatus}
        />
      </box>
    </box>
  );
});
