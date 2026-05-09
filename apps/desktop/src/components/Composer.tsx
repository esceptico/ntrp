import { useEffect, useMemo, useRef } from "react";
import { ArrowUp, ImagePlus, ShieldOff, ShieldCheck, Sparkles, Square, X } from "lucide-react";
import clsx from "clsx";
import { useStore, type ImageBlock } from "../store";
import { enqueueMessage, isBuiltin, respondToAllApprovals, runBuiltinCommand, sendMessage, stopRun, viewSkill } from "../actions";
import { QueueCard } from "./QueueCard";
import {
  CommandPicker,
  filterCommands,
  useCommandList,
  type CommandEntry,
} from "./CommandPicker";
import { ModelReasoningChip } from "./ComposerSelectors";

/** Read a single File and return its bytes as base64 + media type. */
function fileToImageBlock(file: File): Promise<ImageBlock> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Read failed"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Unexpected reader result"));
        return;
      }
      // result is "data:<media_type>;base64,<data>"
      const [meta, data] = result.split(",", 2);
      const m = meta.match(/^data:([^;]+);base64$/);
      resolve({ media_type: m?.[1] ?? file.type ?? "application/octet-stream", data: data ?? "" });
    };
    reader.readAsDataURL(file);
  });
}

/** Returns the slash-prefix at the start of `text` if it currently looks like
 *  a command being composed (no space between the slash and the cursor). */
function pickerQuery(text: string): string | null {
  if (!text.startsWith("/")) return null;
  // Picker stays open while the user is typing the command name (no space yet).
  const head = text.slice(1);
  if (head.includes(" ") || head.includes("\n")) return null;
  return head;
}

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}

function UsageDisplay() {
  const usage = useStore((s) => s.usage);
  if (!usage.lastPrompt && !usage.totalCost) return <span />;
  return (
    <span className="px-1.5 text-[11px] text-faint tabular-nums tracking-[-0.005em] select-none">
      {usage.lastPrompt > 0 && (
        <>
          <strong className="text-muted font-medium">{formatTokens(usage.lastPrompt)}</strong> ctx
        </>
      )}
      {usage.totalCost > 0 && (
        <>
          {usage.lastPrompt > 0 && " · "}
          {formatCost(usage.totalCost)}
        </>
      )}
    </span>
  );
}

function resize(input: HTMLTextAreaElement) {
  input.style.height = "0px";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
}

export function Composer() {
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const running = useStore((s) => s.running);
  const connected = useStore((s) => s.connected);
  const pendingApprovalCount = useStore((s) => s.pendingApprovals.length);
  const editingId = useStore((s) => s.editingId);
  const setEditingId = useStore((s) => s.setEditingId);
  const skipApprovals = useStore((s) => s.skipApprovals);
  const setSkipApprovals = useStore((s) => s.setSkipApprovals);
  const pickerOpen = useStore((s) => s.commandPickerOpen);
  const pickerIndex = useStore((s) => s.commandPickerIndex);
  const setPickerOpen = useStore((s) => s.setCommandPickerOpen);
  const setPickerIndex = useStore((s) => s.setCommandPickerIndex);
  const skills = useStore((s) => s.skills);
  const selectedSkill = useStore((s) => s.selectedSkill);
  const setSelectedSkill = useStore((s) => s.setSelectedSkill);
  const pendingImages = useStore((s) => s.pendingImages);
  const addPendingImages = useStore((s) => s.addPendingImages);
  const removePendingImage = useStore((s) => s.removePendingImage);
  const clearPendingImages = useStore((s) => s.clearPendingImages);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const query = useMemo(() => pickerQuery(draft), [draft]);
  const allCommands = useCommandList();
  const filteredCommands = useMemo(
    () => (query !== null ? filterCommands(allCommands, query) : []),
    [allCommands, query],
  );

  // Track the query for which the user explicitly dismissed the picker (via
  // Escape). The auto-open effect honors this until the query changes.
  const dismissedQueryRef = useRef<string | null>(null);

  // Keep picker open state in sync with the textarea contents.
  useEffect(() => {
    if (query === null) {
      dismissedQueryRef.current = null;
      if (pickerOpen) setPickerOpen(false);
      return;
    }
    if (query === dismissedQueryRef.current) {
      if (pickerOpen) setPickerOpen(false);
      return;
    }
    if (filteredCommands.length === 0) {
      if (pickerOpen) setPickerOpen(false);
      return;
    }
    if (!pickerOpen) setPickerOpen(true);
  }, [query, filteredCommands.length, pickerOpen, setPickerOpen]);

  const hasDraft = draft.trim().length > 0;
  const hasContent = hasDraft || Boolean(selectedSkill) || pendingImages.length > 0;
  // While a run is in flight, submit enqueues onto the active run instead
  // of being blocked. Disable only when disconnected or there's nothing
  // to send.
  const disabled = !connected || !hasContent;

  // Composer shows a "thinking" indicator while we're waiting for the
  // agent's first token (running but no assistant turn streaming yet).
  // Replaces the standalone Thinking row — status lives on the surface
  // that produced the action. The visual variant is user-configurable
  // via Settings → Appearance.
  const order = useStore((s) => s.order);
  const lastRole = useStore((s) =>
    order.length > 0 ? s.messages.get(order[order.length - 1])?.role ?? null : null,
  );
  const awaitingFirstToken = running && lastRole !== "assistant";
  const thinkingStyle = useStore((s) => s.prefs.thinkingAnimation);
  const thinkingIntensity = useStore((s) => s.prefs.thinkingIntensity);

  useEffect(() => {
    if (inputRef.current) resize(inputRef.current);
  }, [draft]);

  function dispatchCommand(text: string): boolean {
    // If the text is a slash-command, route it. Returns true if handled.
    if (!text.startsWith("/")) return false;
    const [head, ...rest] = text.slice(1).split(" ");
    const args = rest.join(" ").trim();
    if (isBuiltin(head)) {
      void runBuiltinCommand(head, args);
      return true;
    }
    return false; // skill or unknown — let sendMessage forward to server
  }

  function applyPickerSelection(entry: CommandEntry) {
    setPickerOpen(false);
    setDraft("");
    if (inputRef.current) {
      inputRef.current.value = "";
      resize(inputRef.current);
    }

    if (entry.kind === "builtin") {
      // Builtins fire-and-forget.
      void runBuiltinCommand(entry.name, "");
      return;
    }

    // Skills attach as a pill above the textarea so the user can type a
    // prompt under the skill before sending. Submit assembles
    // `/<skill-name> <prompt>` and the server's expand_skill_command does
    // the substitution.
    const skill = skills.find((s) => s.name === entry.name);
    if (skill) setSelectedSkill(skill);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function submit() {
    const text = draft;
    const skill = selectedSkill;
    const images = pendingImages;
    if (!text.trim() && !skill && images.length === 0) return;

    setDraft("");
    setSelectedSkill(null);
    clearPendingImages();
    if (inputRef.current) {
      inputRef.current.value = "";
      resize(inputRef.current);
    }
    setPickerOpen(false);

    const trimmed = text.trim();

    // Pending approvals + a typed draft → reject all and enqueue the
    // text as a user message. The rejection itself uses the default
    // feedback ("User rejected this action"); the user's actual
    // wording lands in chat as a real message so it's visible and
    // persists in history. Agent sees both: rejected tool results
    // followed by the user's next message in the conversation.
    if (pendingApprovalCount > 0 && trimmed) {
      void respondToAllApprovals(false);
      void enqueueMessage(trimmed, images);
      return;
    }

    // Pure builtin (no skill, no images) — route to the dispatcher.
    if (!skill && images.length === 0 && dispatchCommand(text)) return;

    const fullText = skill
      ? trimmed.length > 0
        ? `/${skill.name} ${trimmed}`
        : `/${skill.name}`
      : text;
    if (running) {
      void enqueueMessage(fullText, images);
    } else {
      void sendMessage(fullText, images);
    }
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft("");
    if (inputRef.current) {
      inputRef.current.value = "";
      resize(inputRef.current);
    }
  }

  async function attachFiles(fileList: FileList | File[] | null) {
    if (!fileList) return;
    const files = Array.from(fileList).filter((f) => f.type.startsWith("image/"));
    if (files.length === 0) return;
    const blocks = await Promise.all(files.map(fileToImageBlock));
    addPendingImages(blocks);
  }

  // The DVD variant runs as a viewport-wide screensaver, not inside the
  // composer card — pass an empty style to the composer in that case so
  // the in-card animation doesn't duplicate the viewport one.
  const composerThinkingStyle = thinkingStyle === "dvd" ? "" : thinkingStyle;

  return (
    <div className="px-7 pb-[18px]">
      {awaitingFirstToken && thinkingStyle === "dvd" && (
        <div className="dvd-screensaver" aria-hidden>
          <div className="dvd-x">
            <span className="dvd-y">DVD</span>
          </div>
        </div>
      )}
      <div className="max-w-[760px] mx-auto">
        <QueueCard />
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        data-thinking={awaitingFirstToken ? "true" : undefined}
        data-thinking-style={composerThinkingStyle}
        data-thinking-intensity={thinkingIntensity}
        className="composer-card relative max-w-[760px] mx-auto flex flex-col border border-line rounded-[14px] bg-surface focus-within:border-line-strong transition-colors"
      >
        {pickerOpen && query !== null && (
          <CommandPicker query={query} onSelect={applyPickerSelection} />
        )}
        {selectedSkill && (
          <div className="flex items-center gap-2 px-3 pt-2 pb-1.5">
            <button
              type="button"
              onClick={() => void viewSkill(selectedSkill.name)}
              title={selectedSkill.path ?? selectedSkill.name}
              className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-sunken/80 border border-line-soft text-[11.5px] font-medium text-ink-soft hover:bg-surface-soft hover:border-line transition-colors"
            >
              <Sparkles size={11} strokeWidth={2} className="text-accent" />
              <span className="capitalize">{selectedSkill.name.replace(/[_-]/g, " ")}</span>
            </button>
            <button
              type="button"
              onClick={() => setSelectedSkill(null)}
              className="grid place-items-center w-5 h-5 rounded-md text-faint hover:bg-surface-soft hover:text-ink transition-colors"
              title="Detach skill"
              aria-label="Detach skill"
            >
              <X size={11} strokeWidth={2} />
            </button>
          </div>
        )}
        {editingId && (
          <div className="flex items-center gap-2 px-3 py-1.5 text-[11.5px] text-accent-strong bg-accent-soft/40 rounded-t-[14px]">
            <span>Editing previous message — pressing send will replace it.</span>
            <button
              type="button"
              onClick={cancelEdit}
              className="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
              title="Cancel edit"
            >
              <X size={11} strokeWidth={2} />
              cancel
            </button>
          </div>
        )}
        {pendingImages.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-2">
            {pendingImages.map((img, i) => (
              <div key={i} className="relative">
                <img
                  src={`data:${img.media_type};base64,${img.data}`}
                  alt=""
                  className="h-14 w-14 rounded-md object-cover border border-line-soft"
                />
                <button
                  type="button"
                  onClick={() => removePendingImage(i)}
                  aria-label="Remove image"
                  className="absolute -top-1.5 -right-1.5 grid place-items-center w-4 h-4 rounded-full bg-ink text-on-ink shadow-sm hover:bg-black"
                >
                  <X size={9} strokeWidth={2.4} />
                </button>
              </div>
            ))}
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            void attachFiles(e.target.files);
            e.target.value = ""; // allow picking the same file again later
          }}
        />
        <textarea
          ref={inputRef}
          id="message-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Backspace on empty draft + attached skill → detach the skill.
            if (
              e.key === "Backspace" &&
              !pickerOpen &&
              selectedSkill &&
              draft.length === 0
            ) {
              e.preventDefault();
              setSelectedSkill(null);
              return;
            }
            // Esc cancels an in-flight run when the picker isn't open.
            if (e.key === "Escape" && !pickerOpen && running) {
              e.preventDefault();
              void stopRun();
              return;
            }
            if (pickerOpen && filteredCommands.length > 0) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setPickerIndex((pickerIndex + 1) % filteredCommands.length);
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setPickerIndex(
                  (pickerIndex - 1 + filteredCommands.length) % filteredCommands.length,
                );
                return;
              }
              if (e.key === "Tab") {
                e.preventDefault();
                applyPickerSelection(filteredCommands[pickerIndex]);
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                dismissedQueryRef.current = query;
                setPickerOpen(false);
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                applyPickerSelection(filteredCommands[pickerIndex]);
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData?.files ?? []).filter((f) =>
              f.type.startsWith("image/"),
            );
            if (files.length > 0) {
              e.preventDefault();
              void attachFiles(files);
            }
          }}
          rows={1}
          placeholder="Message ntrp…"
          className="w-full min-h-[44px] max-h-[220px] resize-none border-0 bg-transparent px-4 pt-[13px] pb-1 text-[14px] leading-[1.5] text-ink outline-none tracking-[-0.005em] placeholder:text-whisper"
        />
        <div className="flex items-center gap-1.5 px-2 pt-1.5 pb-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="Attach image"
            aria-label="Attach image"
            className="inline-flex items-center justify-center h-7 w-7 rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-colors"
          >
            <ImagePlus size={13} strokeWidth={1.8} />
          </button>
          <button
            type="button"
            onClick={() => setSkipApprovals(!skipApprovals)}
            title={skipApprovals ? "Auto-approving every tool call. Click to require approval." : "Approvals required for sensitive tools. Click to enable YOLO."}
            className={clsx(
              "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] font-medium tracking-[-0.005em] transition-colors select-none",
              skipApprovals
                ? "bg-accent-soft text-accent-strong hover:bg-accent-soft/80"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            )}
          >
            {skipApprovals ? (
              <>
                <ShieldOff size={11} strokeWidth={2} />
                YOLO
              </>
            ) : (
              <>
                <ShieldCheck size={11} strokeWidth={2} />
                Approve
              </>
            )}
          </button>
          <UsageDisplay />
          <span className="flex-1" />
          <ModelReasoningChip />
          {running ? (
            <button
              type="button"
              onClick={() => void stopRun()}
              aria-label="Stop"
              title="Stop (Esc)"
              className="grid place-items-center w-7 h-7 rounded-full bg-ink text-on-ink shadow-[0_1px_2px_rgba(0,0,0,0.2)] hover:opacity-90 transition-opacity"
            >
              <Square size={11} strokeWidth={0} fill="currentColor" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled}
              data-send="true"
              aria-label="Send"
              className="grid place-items-center w-7 h-7 rounded-full bg-ink text-on-ink shadow-[0_1px_2px_rgba(0,0,0,0.2)] hover:opacity-90 disabled:opacity-40 disabled:shadow-none transition-opacity"
            >
              <ArrowUp size={13} strokeWidth={2.4} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
