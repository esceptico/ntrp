import { useMemo } from "react";
import { Bot, Square, X } from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import { useStore, type ActivityItem } from "@/stores";
import { highlight } from "@/lib/highlight";
import { activityItemStatus, friendlyAgentLabel, isAgent } from "@/lib/agent";
import { IconButton } from "@/components/ui/IconButton";
import { PageModal } from "@/components/ui/PageModal";
import { ScrollFadeTop } from "@/components/ui/ScrollBlur";
import { ICON } from "@/lib/icons";
import { cancelSubagent } from "@/actions/messages";
import { formatMaybeJson } from "@/features/chat/lib/toolViewer";
import { AgentBody } from "@/features/chat/components/AgentBody";
import { ChildRuns } from "@/features/chat/components/ChildRuns";
import { Section } from "@/features/chat/components/ToolViewerSection";

export function ToolViewer() {
  const item = useStore((s) => s.viewingTool);
  const close = useStore((s) => s.setViewingTool);

  // Re-read the live item from the store so a streaming result patches in
  // while the viewer is open. The selector returns a stable reference for
  // the matching activity item — Zustand's default reference equality is
  // fine here.
  const live = useStore((s) => {
    if (!item) return null;
    for (const msg of s.messages.values()) {
      if (!msg.activity) continue;
      const found = msg.activity.items.find((it) => it.id === item.id);
      if (found) return found;
    }
    return item;
  });

  // All activity items reachable from this tool through `parentToolId`. We
  // need the full descendant set so the agent inspector can render a tree
  // of nested tool calls; the regular tool inspector only shows direct
  // children. Wrapped in useShallow so reference equality stays stable
  // across unrelated store updates.
  const descendants = useStore(
    useShallow((s) => {
      if (!item) return [] as ActivityItem[];
      const childrenByParent = new Map<string, ActivityItem[]>();
      for (const msg of s.messages.values()) {
        if (!msg.activity) continue;
        for (const it of msg.activity.items) {
          if (!it.parentToolId) continue;
          const arr = childrenByParent.get(it.parentToolId) ?? [];
          arr.push(it);
          childrenByParent.set(it.parentToolId, arr);
        }
      }
      const out: ActivityItem[] = [];
      const seen = new Set<string>();
      const visit = (parentId: string) => {
        const kids = childrenByParent.get(parentId);
        if (!kids) return;
        for (const k of kids) {
          if (seen.has(k.id)) continue;
          seen.add(k.id);
          out.push(k);
          visit(k.id);
        }
      };
      visit(item.id);
      return out;
    }),
  );

  // Direct children only — what the regular tool inspector shows.
  const directChildren = useMemo(
    () => descendants.filter((it) => it.parentToolId === item?.id),
    [descendants, item?.id],
  );

  const input = useMemo(() => formatMaybeJson(live?.args), [live?.args]);
  const output = useMemo(() => formatMaybeJson(live?.result), [live?.result]);
  const inputHtml = useMemo(
    () => (input.lang ? highlight(input.body, input.lang) : ""),
    [input.body, input.lang],
  );
  const outputHtml = useMemo(
    () => (output.lang ? highlight(output.body, output.lang) : ""),
    [output.body, output.lang],
  );

  const open = !!(item && live);
  const canStopSubagent =
    !!live && isAgent(live) && live.taskStatus === "running" && !!live.runId && !live.cancelRequested;

  return (
    <PageModal
      open={open}
      onClose={() => close(null)}
      size="w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)]"
      ariaLabel="Tool details"
    >
      <header className="modal-header flex items-start justify-between gap-3.5 min-w-0">
        <div className="min-w-0 flex-1 flex items-center gap-2.5">
          {live && isAgent(live) && (
            <span
              aria-hidden
              className="grid place-items-center w-[22px] h-[22px] rounded-md bg-accent-soft text-accent-strong shrink-0"
            >
              <Bot size={ICON.XS} strokeWidth={2} />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="text-lg font-semibold tracking-[-0.012em] text-ink truncate">
              {live && isAgent(live)
                ? live.displayName ?? friendlyAgentLabel(live.kind)
                : live?.kind}
            </div>
            {live && !isAgent(live) && live.target && live.target !== live.kind && (
              <div className="mt-0.5 text-xs text-faint font-mono truncate">
                {live.target}
              </div>
            )}
          </div>
        </div>
        {canStopSubagent && live && (
          <IconButton
            onClick={() => {
              if (live.runId) void cancelSubagent(live.runId, live.id);
            }}
            aria-label="Stop subagent"
            title="Stop subagent"
            className="shrink-0"
          >
            <Square size={ICON.SM} strokeWidth={2} />
          </IconButton>
        )}
        <IconButton onClick={() => close(null)} aria-label="Close" className="shrink-0">
          <X size={ICON.SM} strokeWidth={2} />
        </IconButton>
      </header>

      <div className="overflow-y-auto scroll-thin px-5 py-4 grid grid-cols-[minmax(0,1fr)] gap-4 min-w-0">
        <ScrollFadeTop />
        {live && isAgent(live) ? (
          <AgentBody item={live} descendants={descendants} />
        ) : (
          <>
            <Section
              title="Input"
              body={input.body}
              html={inputHtml}
              placeholder="No input arguments."
            />
            <Section
              title="Output"
              body={output.body}
              html={outputHtml}
              placeholder={live && activityItemStatus(live) === "ongoing" ? "Waiting for result…" : "Empty result."}
            />
            {directChildren.length > 0 && <ChildRuns items={directChildren} />}
          </>
        )}
      </div>
    </PageModal>
  );
}
