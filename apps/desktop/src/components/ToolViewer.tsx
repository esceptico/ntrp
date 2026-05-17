import { useMemo } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Bot, Check, Copy, X } from "lucide-react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore, type ActivityItem } from "../store";
import { highlight } from "../highlight";
import { extractTask, friendlyAgentLabel, isAgent } from "../lib/agent";
import { Markdown } from "./Markdown";
import { IconButton } from "./IconButton";
import {
  ENTRY_GLASS,
  ENTRY_LINEN,
  EASE_DECELERATE,
} from "../lib/tokens/motion";
import { useEscapeKey, useTimeoutFlag } from "../lib/hooks";
import { ICON } from "../lib/icons";

/** Pretty-print JSON; fall back to the raw string when parse fails. The
 *  `lang` field is set to "json" when we successfully reformatted, so the
 *  viewer can syntax-highlight only when we actually have JSON. */
function formatMaybeJson(raw: string | undefined): { body: string; lang: string } {
  if (!raw) return { body: "", lang: "" };
  const trimmed = raw.trim();
  if (!trimmed) return { body: "", lang: "" };
  try {
    return { body: JSON.stringify(JSON.parse(trimmed), null, 2), lang: "json" };
  } catch {
    return { body: raw, lang: "" };
  }
}

export function ToolViewer() {
  const item = useStore((s) => s.viewingTool);
  const close = useStore((s) => s.setViewingTool);
  const material = useStore((s) => s.prefs.material);
  const isGlass = material === "glass";
  const panelTransition = isGlass
    ? { duration: ENTRY_GLASS.duration, ease: ENTRY_GLASS.ease }
    : ENTRY_LINEN.spring;

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

  useEscapeKey(() => close(null), !!item);

  const root = document.querySelector("#app");
  if (!root) return null;
  const open = !!(item && live);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="tool-viewer"
          className="modal-scrim absolute inset-0 z-50 grid place-items-center p-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE_DECELERATE }}
          onClick={() => close(null)}
        >
          <motion.div
            className="glass-surface glass-radius-md w-[min(720px,calc(100vw-80px))] max-w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden"
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={panelTransition}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-start justify-between gap-3.5 px-5 pt-[18px] pb-3 min-w-0">
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
                    {live && isAgent(live) ? friendlyAgentLabel(live.kind) : live?.kind}
                  </div>
                  {live && !isAgent(live) && live.target && live.target !== live.kind && (
                    <div className="mt-0.5 text-xs text-faint font-mono truncate">
                      {live.target}
                    </div>
                  )}
                </div>
              </div>
              <IconButton onClick={() => close(null)} aria-label="Close" className="shrink-0">
                <X size={ICON.SM} strokeWidth={2} />
              </IconButton>
            </header>

            <div className="overflow-y-auto scroll-thin scroll-fade-top px-5 py-4 grid grid-cols-[minmax(0,1fr)] gap-4 min-w-0">
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
                    placeholder={live?.result == null ? "Waiting for result…" : "Empty result."}
                  />
                  {directChildren.length > 0 && <ChildRuns items={directChildren} />}
                </>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}

function formatAgentUsage(tokens: number, cost: number | undefined): string {
  const tk =
    tokens < 1000
      ? `${tokens}`
      : tokens < 10000
        ? `${(tokens / 1000).toFixed(1)}k`
        : `${Math.round(tokens / 1000)}k`;
  if (!cost) return `${tk} tokens`;
  const ct = cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(3)}`;
  return `${tk} tokens · ${ct}`;
}

function AgentBody({
  item,
  descendants,
}: {
  item: ActivityItem;
  descendants: ActivityItem[];
}) {
  const task = useMemo(() => extractTask(item.args) ?? item.target, [item.args, item.target]);
  const stats = useMemo(() => buildStats(descendants), [descendants]);

  return (
    <>
      <section className="grid gap-1.5">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="m-0 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
            Task
          </h3>
          {item.usage && item.usage.total > 0 && (
            <span className="text-xs text-faint tabular-nums" title="Subagent's own LLM spend (already rolled into the parent's total cost)">
              {formatAgentUsage(item.usage.total, item.cost)}
            </span>
          )}
        </div>
        <p className="m-0 text-base leading-relaxed text-ink whitespace-pre-wrap">
          {task || "(no task provided)"}
        </p>
      </section>

      <section className="grid gap-1.5">
        <div className="flex items-center gap-2">
          <h3 className="m-0 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
            Result
          </h3>
          {item.result != null && item.result.length > 0 && (
            <CopyButton getValue={() => item.result ?? ""} />
          )}
        </div>
        {item.result == null ? (
          <div className="px-3 py-2.5 rounded-[10px] bg-surface-soft text-sm text-faint italic">
            Working…
          </div>
        ) : item.result.trim().length === 0 ? (
          <div className="px-3 py-2.5 rounded-[10px] bg-surface-soft text-sm text-faint italic">
            Empty result.
          </div>
        ) : (
          <div className="rounded-[10px] border border-line-soft bg-bg-main px-3 py-2.5 max-h-[40vh] overflow-y-auto scroll-thin min-w-0">
            <Markdown content={item.result} />
          </div>
        )}
      </section>

      {descendants.length > 0 && (
        <section className="grid gap-1.5 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="m-0 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
              Activity
            </h3>
            <span className="text-xs text-faint tabular-nums">
              {stats.total} {stats.total === 1 ? "call" : "calls"}
              {stats.agents > 0 && ` · ${stats.agents} sub-agent${stats.agents === 1 ? "" : "s"}`}
            </span>
          </div>
          <ActivityTree
            descendants={descendants}
            rootId={item.id}
            rootDepth={item.depth ?? 0}
          />
        </section>
      )}
    </>
  );
}

function ActivityTree({
  descendants,
  rootId,
  rootDepth,
}: {
  descendants: ActivityItem[];
  rootId: string;
  rootDepth: number;
}) {
  const setViewing = useStore((s) => s.setViewingTool);
  const childrenByParent = useMemo(() => {
    const map = new Map<string, ActivityItem[]>();
    for (const it of descendants) {
      if (!it.parentToolId) continue;
      const arr = map.get(it.parentToolId) ?? [];
      arr.push(it);
      map.set(it.parentToolId, arr);
    }
    return map;
  }, [descendants]);

  return (
    <div className="rounded-[10px] border border-line-soft bg-surface overflow-hidden">
      <ActivityTreeBranch
        parentId={rootId}
        baseDepth={rootDepth + 1}
        childrenByParent={childrenByParent}
        onPick={setViewing}
      />
    </div>
  );
}

function ActivityTreeBranch({
  parentId,
  baseDepth,
  childrenByParent,
  onPick,
}: {
  parentId: string;
  baseDepth: number;
  childrenByParent: Map<string, ActivityItem[]>;
  onPick: (item: ActivityItem) => void;
}) {
  const kids = childrenByParent.get(parentId);
  if (!kids || kids.length === 0) return null;
  return (
    <ul className="m-0 p-0 list-none">
      {kids.map((child) => (
        <ActivityTreeNode
          key={child.id}
          item={child}
          baseDepth={baseDepth}
          childrenByParent={childrenByParent}
          onPick={onPick}
        />
      ))}
    </ul>
  );
}

function ActivityTreeNode({
  item,
  baseDepth,
  childrenByParent,
  onPick,
}: {
  item: ActivityItem;
  baseDepth: number;
  childrenByParent: Map<string, ActivityItem[]>;
  onPick: (item: ActivityItem) => void;
}) {
  const indent = ((item.depth ?? baseDepth) - baseDepth) * 16 + 12;
  const agent = isAgent(item);
  const label = agent ? friendlyAgentLabel(item.kind) : item.kind;
  const detail = agent ? extractTask(item.args) ?? item.target : item.target;
  const running = item.result == null;
  return (
    <li className="m-0 p-0">
      <button
        type="button"
        onClick={() => onPick(item)}
        style={{ paddingLeft: indent }}
        className="app-row flex items-center gap-2 w-full pr-3 py-1.5 text-left bg-transparent border-0 text-ink-soft min-w-0"
      >
        {agent ? (
          <span
            aria-hidden
            className="grid place-items-center w-[16px] h-[16px] rounded-[4px] bg-accent-soft text-accent-strong shrink-0"
          >
            <Bot size={ICON.XS} strokeWidth={2} />
          </span>
        ) : (
          <ArrowRight size={ICON.XS} strokeWidth={2} className="text-whisper shrink-0" />
        )}
        <span
          className={clsx(
            "text-sm shrink-0",
            agent ? "font-medium text-ink-soft" : "font-mono text-ink-soft",
          )}
        >
          {label}
        </span>
        {detail && (
          <span
            className={clsx(
              "truncate min-w-0 flex-1 text-xs",
              agent ? "text-faint" : "text-faint font-mono",
            )}
          >
            {detail}
          </span>
        )}
        {running && (
          <span className="text-2xs uppercase tracking-[0.08em] text-faint shrink-0">
            running
          </span>
        )}
      </button>
      <ActivityTreeBranch
        parentId={item.id}
        baseDepth={baseDepth}
        childrenByParent={childrenByParent}
        onPick={onPick}
      />
    </li>
  );
}

function buildStats(descendants: ActivityItem[]) {
  let agents = 0;
  for (const d of descendants) if (isAgent(d)) agents++;
  return { total: descendants.length, agents };
}

function CopyButton({ getValue }: { getValue: () => string }) {
  const [copied, flashCopied] = useTimeoutFlag(1200);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(getValue());
      flashCopied();
    } catch {
      /* ignore */
    }
  };
  return (
    <button
      type="button"
      onClick={() => void onCopy()}
      aria-label={copied ? "Copied" : "Copy"}
      className={clsx(
        "ml-auto inline-flex items-center gap-1 h-6 px-1.5 rounded-md text-xs font-medium tracking-[-0.005em] transition-colors",
        copied ? "text-accent-strong bg-accent-soft" : "text-muted hover:bg-surface-soft hover:text-ink",
      )}
    >
      {copied ? <Check size={ICON.XS} strokeWidth={2.4} /> : <Copy size={ICON.XS} strokeWidth={2} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function ChildRuns({ items }: { items: ActivityItem[] }) {
  const setViewing = useStore((s) => s.setViewingTool);
  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0">
      <h3 className="m-0 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
        Child runs
      </h3>
      <ul className="grid gap-px m-0 p-0 list-none rounded-[10px] border border-line-soft bg-surface overflow-hidden">
        {items.map((child) => (
          <li key={child.id} className="contents">
            <button
              type="button"
              onClick={() => setViewing(child)}
              className="app-row flex items-baseline gap-2 w-full px-3 py-2 text-left bg-transparent border-0 text-ink-soft"
            >
              <ArrowRight size={ICON.XS} strokeWidth={2} className="self-center text-whisper shrink-0" />
              <span className="text-sm font-medium text-ink-soft shrink-0">{child.kind}</span>
              <span className="text-xs text-faint font-mono truncate min-w-0 flex-1">
                {child.target}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Section({
  title,
  body,
  html,
  placeholder,
}: {
  title: string;
  body: string;
  html: string;
  placeholder: string;
}) {
  const [copied, flashCopied] = useTimeoutFlag(1200);
  const hasBody = body.trim().length > 0;

  const onCopy = async () => {
    if (!hasBody) return;
    try {
      await navigator.clipboard.writeText(body);
      flashCopied();
    } catch {
      /* clipboard refused — silently ignore */
    }
  };

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0">
      <div className="flex items-center gap-2">
        <h3 className="m-0 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
          {title}
        </h3>
        {hasBody && (
          <button
            type="button"
            onClick={() => void onCopy()}
            aria-label={copied ? "Copied" : "Copy"}
            className={clsx(
              "ml-auto inline-flex items-center gap-1 h-6 px-1.5 rounded-md text-xs font-medium tracking-[-0.005em] transition-colors",
              copied
                ? "text-accent-strong bg-accent-soft"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            )}
          >
            {copied ? <Check size={ICON.XS} strokeWidth={2.4} /> : <Copy size={ICON.XS} strokeWidth={2} />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
      {hasBody ? (
        html ? (
          <pre
            className="hljs m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-[12.25px] leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap break-all max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre className="m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-[12.25px] leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap break-all max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin">
            {body}
          </pre>
        )
      ) : (
        <div className="px-3 py-2.5 rounded-[10px] bg-surface-soft text-sm text-faint italic">
          {placeholder}
        </div>
      )}
    </section>
  );
}
