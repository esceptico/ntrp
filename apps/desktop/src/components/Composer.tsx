import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Box, Check, ImagePlus, Pencil, ShieldOff, ShieldCheck, Square, Target, X } from "lucide-react";
import clsx from "clsx";
import { useStore, type ImageBlock } from "../store";
import {
  acceptGoalProposal,
  cancelGoalProposal,
  editGoalProposal,
  enqueueMessage,
  isBuiltin,
  respondToAllApprovals,
  runBuiltinCommand,
  sendMessage,
  stopRun,
  toggleAuto,
  viewSkill,
} from "../actions";
import { QueueCard } from "./QueueCard";
import { GoalStatusBar } from "./GoalStrip";
import { CommandPicker } from "./CommandPicker";
import { Chip } from "./Chip";
import { BlurSwap } from "./BlurSwap";
import { ModelReasoningChip } from "./ComposerSelectors";
import { LoopStatusBar } from "./composer/LoopStatus";
import { BudgetDial } from "./composer/BudgetDial";
import { useListNav, useTimeoutFlag } from "../lib/hooks";
import { ICON } from "../lib/icons";
import { DISSOLVE_OUT, EASE_OUT, MOTION, RISE_IN, RISE_SETTLED } from "../lib/tokens/motion";
import { awaitingFirstRunOutput } from "../lib/runIndicators";
import { filterCommands, useCommandList, type CommandEntry } from "../lib/commands";

// Composer sub-sections (editing banner, image strip, skill pill, goal
// proposal) rise into focus on mount and dissolve out faster on unmount;
// the composer's height snaps at the AnimatePresence boundary.
const SECTION_ENTER = { duration: MOTION.row, ease: EASE_OUT };
const SECTION_EXIT = { ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } };

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
  const pendingGoalProposal = useStore((s) => s.pendingGoalProposal);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const query = useMemo(() => pickerQuery(draft), [draft]);
  const allCommands = useCommandList();
  const filteredCommands = useMemo(
    () => (query !== null ? filterCommands(allCommands, query) : []),
    [allCommands, query],
  );

  const pickerNav = useListNav(
    filteredCommands.length,
    (i) => {
      const entry = filteredCommands[i];
      if (entry) applyPickerSelection(entry);
    },
    { index: pickerIndex, setIndex: setPickerIndex },
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
  const messages = useStore((s) => s.messages);
  const currentRunId = useStore((s) => s.currentRunId);
  const thinkingRunId = useStore((s) => s.thinkingRunId);
  const indicatorMessages = useMemo(
    () =>
      order
        .map((id) => messages.get(id))
        .filter((message): message is NonNullable<typeof message> => message !== undefined),
    [order, messages],
  );
  const serverThinking = Boolean(thinkingRunId && (!currentRunId || thinkingRunId === currentRunId));
  const awaitingFirstToken = serverThinking || awaitingFirstRunOutput(running, indicatorMessages);
  // 350ms threshold — fast replies (cached, small models, short tool
  // chains) shouldn't briefly flash the indicator. If the agent starts
  // emitting within the threshold, awaitingFirstToken flips false before
  // the timer fires and the indicator never appears. This is the
  // "spinner only when actually slow" pattern from ChatGPT/Cursor.
  const [showThinking, setShowThinking] = useState(false);
  // When the rim's been visible and the agent's first token arrives,
  // hold the rim mounted for ~250ms in a "leaving" state so its exit
  // can fade rather than hard-cut. Beat 1 of the thinking → streaming
  // transition pass.
  const [thinkingLeaving, setThinkingLeaving] = useState(false);
  useEffect(() => {
    if (!awaitingFirstToken) {
      if (showThinking) {
        setThinkingLeaving(true);
        const id = window.setTimeout(() => {
          setShowThinking(false);
          setThinkingLeaving(false);
        }, 250);
        return () => window.clearTimeout(id);
      }
      return;
    }
    setThinkingLeaving(false);
    const id = window.setTimeout(() => setShowThinking(true), 350);
    return () => window.clearTimeout(id);
  }, [awaitingFirstToken, showThinking]);
  const thinkingStyle = useStore((s) => s.prefs.thinkingAnimation);
  const thinkingIntensity = useStore((s) => s.prefs.thinkingIntensity);
  // Brief programmatic "press" on the send button. The button's :active
  // pseudo doesn't fire when Enter submits the form (no actual click).
  // This gives keyboard submits the same tactile feedback as a mouse
  // click — the button shrinks for ~140ms each time submit() runs.
  const [sendPressing, flashSendPress] = useTimeoutFlag(140);
  // Composer-level send acknowledgement — the panel fill brightens for
  // a single beat (280ms) on submit. It composes alongside the
  // thinking-rim ::before since this lives on a separate ::after
  // pseudo-element in CSS.
  const [justSent, flashJustSent] = useTimeoutFlag(280);

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

  return (
    <div className="px-7 pb-2">
      <div className="max-w-[760px] mx-auto">
        <QueueCard />
      </div>
      <AnimatePresence initial={false}>
        {pendingGoalProposal && (
          <GoalProposalCard key="goal-proposal" objective={pendingGoalProposal.objective} />
        )}
      </AnimatePresence>
      {/* Wrapper exists so the CommandPicker can sit as a sibling of
          the form rather than a child and avoid being clipped by the
          composer panel. */}
      <div className="composer-wrap relative max-w-[760px] mx-auto">
        {pickerOpen && query !== null && (
          <CommandPicker query={query} onSelect={applyPickerSelection} />
        )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          flashSendPress();
          flashJustSent();
          submit();
        }}
        data-thinking={showThinking ? "true" : undefined}
        data-thinking-leaving={thinkingLeaving ? "true" : undefined}
        data-thinking-style={thinkingStyle}
        data-thinking-intensity={thinkingIntensity}
        data-just-sent={justSent ? "true" : undefined}
        className="composer-card surface-panel surface-radius-md relative flex flex-col"
      >
        <AnimatePresence initial={false}>
          {editingId && (
            <motion.div
              key="editing-banner"
              initial={RISE_IN}
              animate={RISE_SETTLED}
              exit={SECTION_EXIT}
              transition={SECTION_ENTER}
              className="flex items-center gap-2 px-3 py-1.5 text-xs text-accent-strong bg-accent-soft/40 rounded-t-[14px]"
            >
              <span>Editing previous message — pressing send will replace it.</span>
              <button
                type="button"
                onClick={cancelEdit}
                className="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97]"
                title="Cancel edit"
              >
                <X size={ICON.SM} strokeWidth={2} />
                cancel
              </button>
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence initial={false}>
          {pendingImages.length > 0 && (
            <motion.div
              key="pending-images"
              initial={RISE_IN}
              animate={RISE_SETTLED}
              exit={SECTION_EXIT}
              transition={SECTION_ENTER}
              className="flex flex-wrap gap-2 px-3 pt-2"
            >
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
                    className="absolute -top-1.5 -right-1.5 grid place-items-center w-4 h-4 rounded-full bg-ink text-on-ink shadow-sm hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.94]"
                  >
                    <X size={ICON.XS} strokeWidth={2.4} />
                  </button>
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
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
        <div className="flex min-h-[64px] items-start gap-2 px-4 pt-[13px] pb-1">
          <AnimatePresence initial={false}>
            {selectedSkill && (
              <motion.button
                key="skill-pill"
                type="button"
                initial={RISE_IN}
                animate={RISE_SETTLED}
                exit={SECTION_EXIT}
                transition={SECTION_ENTER}
                onClick={() => void viewSkill(selectedSkill.name)}
                title={`${selectedSkill.path ?? selectedSkill.name} - Backspace on empty input detaches`}
                className="mt-[1px] inline-flex max-w-[240px] shrink-0 items-baseline gap-1.5 truncate text-md leading-[1.5] text-info hover:text-accent-strong transition-colors"
              >
                <Box size={ICON.MD} strokeWidth={2} className="relative top-[1px] shrink-0" />
                <span className="truncate capitalize">{selectedSkill.name.replace(/[_-]/g, " ")}</span>
              </motion.button>
            )}
          </AnimatePresence>
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
                if (
                  e.key === "ArrowDown" ||
                  e.key === "ArrowUp" ||
                  (e.key === "Enter" && !e.shiftKey)
                ) {
                  pickerNav.onKeyDown(e);
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
            placeholder={selectedSkill ? "if needed" : "Message ntrp…"}
            className="min-h-[44px] max-h-[220px] min-w-0 flex-1 resize-none border-0 bg-transparent p-0 text-md leading-[1.5] text-ink outline-none tracking-[-0.005em] placeholder:text-muted"
          />
        </div>
        <div className="composer-toolbar flex items-center gap-1.5 px-2 pt-1.5 pb-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="Attach image"
            aria-label="Attach image"
            className="inline-flex items-center justify-center h-7 w-7 rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.94]"
          >
            <ImagePlus size={ICON.LG} strokeWidth={2} />
          </button>
          <Chip
            size="sm"
            active={skipApprovals}
            tone="accent"
            leading={
              <BlurSwap swapKey={skipApprovals ? "auto" : "approve"}>
                {skipApprovals ? <ShieldOff size={ICON.SM} strokeWidth={2} /> : <ShieldCheck size={ICON.SM} strokeWidth={2} />}
              </BlurSwap>
            }
            onClick={() => void toggleAuto(!skipApprovals)}
            title={skipApprovals ? "Auto-approving every tool call. Click to require approval." : "Approvals required for sensitive tools. Click to enable Auto mode."}
            aria-label={skipApprovals ? "Auto-approve enabled — click to require approval" : "Click to enable auto-approve"}
          >
            <span className="composer-chip-label">{skipApprovals ? "Auto" : "Approve"}</span>
          </Chip>
          <LoopStatusBar />
          <GoalStatusBar />
          <span className="flex-1" />
          <BudgetDial />
          <ModelReasoningChip />
          {/* One persistent button so the glyph genuinely swaps (rotate+fade)
              between send and stop instead of the button remounting. */}
          <button
            type={running ? "button" : "submit"}
            onClick={running ? () => void stopRun() : undefined}
            disabled={!running && disabled}
            data-send={running ? undefined : "true"}
            aria-label={running ? "Stop" : "Send"}
            title={running ? "Stop (Esc)" : undefined}
            // active:scale handles mouse press; sendPressing covers keyboard
            // Enter (form-submit doesn't fire :active). Both look identical.
            className={clsx(
              "grid place-items-center w-7 h-7 rounded-full bg-ink text-on-ink shadow-sm hover:opacity-90 disabled:opacity-[0.45] disabled:shadow-none transition-[opacity,scale] duration-fast ease-out active:scale-[0.92]",
              sendPressing && "scale-[0.92]",
            )}
          >
            <AnimatePresence initial={false}>
              <motion.span
                key={running ? "stop" : "send"}
                className="col-start-1 row-start-1 grid place-items-center"
                initial={{ opacity: 0, rotate: -18, scale: 0.92, filter: "blur(4px)" }}
                animate={{ opacity: 1, rotate: 0, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, rotate: 18, scale: 0.92, filter: "blur(4px)" }}
                transition={{ duration: MOTION.palette, ease: EASE_OUT }}
              >
                {running ? (
                  <Square size={ICON.SM} strokeWidth={0} fill="currentColor" />
                ) : (
                  <ArrowUp size={ICON.LG} strokeWidth={2.4} />
                )}
              </motion.span>
            </AnimatePresence>
          </button>
        </div>
      </form>
      </div>
    </div>
  );
}

function GoalProposalCard({ objective }: { objective: string }) {
  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={SECTION_EXIT}
      transition={SECTION_ENTER}
      className="max-w-[760px] mx-auto mb-2"
    >
      <div className="surface-panel surface-radius-md flex items-start gap-2 px-3 py-2">
        <Target size={ICON.MD} strokeWidth={2} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-2xs font-medium text-muted">Proposed goal</div>
          <div className="max-h-10 overflow-hidden text-sm leading-5 text-ink-soft">{objective}</div>
        </div>
        <button
          type="button"
          onClick={() => void acceptGoalProposal()}
          title="Accept goal"
          aria-label="Accept goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink text-on-ink hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.94]"
        >
          <Check size={ICON.SM} strokeWidth={2.4} />
        </button>
        <button
          type="button"
          onClick={editGoalProposal}
          title="Edit goal"
          aria-label="Edit goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.94]"
        >
          <Pencil size={ICON.SM} strokeWidth={2} />
        </button>
        <button
          type="button"
          onClick={cancelGoalProposal}
          title="Cancel goal"
          aria-label="Cancel goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.94]"
        >
          <X size={ICON.SM} strokeWidth={2} />
        </button>
      </div>
    </motion.div>
  );
}
