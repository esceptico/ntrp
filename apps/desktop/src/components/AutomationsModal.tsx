import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Bell,
  Briefcase,
  CalendarClock,
  Circle,
  Clock,
  FileSearch,
  FileText,
  GitPullRequest,
  History,
  Inbox,
  Mail,
  Play,
  Plus,
  Radio,
  Sparkles,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import {
  SPRING_LAYOUT,
  ROW_EXIT,
  RISE_IN,
  RISE_SETTLED,
  EASE_DECELERATE,
  EASE_OUT,
  MOTION,
} from "@/lib/tokens/motion";
import { useStore } from "@/store";
import {
  deleteAutomation,
  dismissSuggestion,
  fetchAutomations,
  fetchAutomationSuggestions,
  runAutomation,
  switchSession,
  toggleAutomation,
} from "@/actions";
import {
  listAutomationRunsApi,
  suggestionToPayload,
  type Automation,
  type AutomationRun,
  type AutomationSuggestion,
} from "@/api";
import { isChannelAutomation, splitAutomationsForTabs } from "@/lib/automationFilters";
import { automationTrustLabel, automationTrustTone } from "@/lib/automationTrust";
import { agentRunFromAutomation, formatRelative, formatTrigger } from "@/lib/agentRun";
import { AutomationEditor, type EditorSeed } from "@/components/automations/AutomationEditor";
import { templatesByCategory, type AutomationTemplate } from "@/components/automations/templates";
import { AgentRunContent, type AgentRunAction } from "@/components/agents/AgentRunRow";
import { Badge } from "@/components/Badge";
import { PageModal } from "@/components/PageModal";
import { ICON } from "@/lib/icons";
import { ScrollFadeTop } from "@/components/ScrollBlur";
import { Tab as TabItem, Tabs } from "@/components/ui/Tabs";
import { TabPanels, useTabDirection } from "@/components/ui/TabPanels";
import { Tooltip } from "@/components/ui/Tooltip";
import { ShowMore } from "@/components/ui/ShowMore";

type Tab = "active" | "system" | "templates";

const TAB_ORDER: Tab[] = ["active", "system", "templates"];

export function AutomationsModal() {
  const open = useStore((s) => s.automationsOpen);
  const close = useStore((s) => s.closeAutomations);
  const automations = useStore((s) => s.automations);
  const [editor, setEditor] = useState<EditorSeed | null>(null);
  const [tab, setTab] = useState<Tab>("active");

  useEffect(() => {
    if (!open) return;
    void fetchAutomations();
    void fetchAutomationSuggestions();
  }, [open]);

  // When the user has nothing yet, default the page to Templates so the
  // empty Active tab doesn't feel like a dead end.
  useEffect(() => {
    if (!open) return;
    if (automations !== null && automations.length === 0) setTab("templates");
  }, [open, automations]);

  const automationGroups = useMemo(() => (automations ? splitAutomationsForTabs(automations) : null), [automations]);
  const activeCount = automationGroups?.user.length ?? 0;
  const systemCount = automationGroups?.internal.length ?? 0;

  const direction = useTabDirection(TAB_ORDER, tab);
  const scrollRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [open, tab]);

  return (
    <>
      <PageModal
        open={open}
        onClose={close}
        disableEscape={!!editor}
        header={{
          title: "Automations",
          actions: (
            <button
              type="button"
              onClick={() => setEditor({ kind: "create" })}
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.97]"
            >
              <Plus size={ICON.XS} strokeWidth={2.2} />
              New
            </button>
          ),
        }}
      >
        <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
          <Tabs
            value={tab}
            onChange={(v) => setTab(v as Tab)}
            variant="underline"
            className="items-center gap-5 px-6"
          >
            <AutomationTab value="active" label="Active" count={activeCount} />
            <AutomationTab value="system" label="System" count={systemCount} />
            <AutomationTab value="templates" label="Templates" />
          </Tabs>

          <div className="relative min-h-0 overflow-hidden">
            {/* Scroll lives outside TabPanels — motion transform breaks sticky overlays. */}
            <div ref={scrollRef} className="h-full min-h-0 overflow-y-auto scroll-thin">
              <ScrollFadeTop key={tab} />
              <TabPanels value={tab} direction={direction} className="px-6 py-5">
                {tab === "active" ? (
                  <ActiveList
                    automations={automationGroups?.user ?? null}
                    onEdit={(automation) => setEditor({ kind: "edit", automation })}
                    onPickTemplate={() => setTab("templates")}
                    onCreate={() => setEditor({ kind: "create" })}
                  />
                ) : tab === "system" ? (
                  <SystemList automations={automationGroups?.internal ?? null} />
                ) : (
                  <TemplatesList
                    onPick={(template) => setEditor({ kind: "create", preset: template.payload })}
                    onPickSuggestion={(s) => setEditor({ kind: "create", preset: suggestionToPayload(s) })}
                  />
                )}
              </TabPanels>
            </div>
          </div>
        </div>
      </PageModal>
      <AutomationEditor seed={editor} onClose={() => setEditor(null)} />
    </>
  );
}

function AutomationTab({
  value,
  label,
  count,
}: {
  value: string;
  label: string;
  count?: number;
}) {
  return (
    <TabItem
      value={value}
      className="inline-flex h-9 items-center gap-1.5 text-base font-medium tracking-[-0.005em] text-muted transition-colors hover:text-ink data-[active=true]:text-ink"
    >
      {label}
      {count != null && count > 0 && (
        <span className="inline-flex h-[18px] min-w-[20px] items-center justify-center rounded-full px-1.5 text-2xs font-medium tabular-nums bg-surface-soft text-muted group-data-[active=true]:bg-ink group-data-[active=true]:text-on-ink">
          {count}
        </span>
      )}
    </TabItem>
  );
}

// ─── Active list ────────────────────────────────────────────────────

function ActiveList({
  automations,
  onEdit,
  onPickTemplate,
  onCreate,
}: {
  automations: Automation[] | null;
  onEdit: (a: Automation) => void;
  onPickTemplate: () => void;
  onCreate: () => void;
}) {
  if (automations === null) {
    return <div className="text-sm text-muted">Loading…</div>;
  }
  if (automations.length === 0) {
    return (
      <div className="grid gap-2 max-w-[420px] py-10">
        <div className="text-md font-medium text-ink">No automations yet.</div>
        <div className="text-sm text-muted leading-[1.5]">
          Start from a template, or write a prompt and a schedule from scratch.
        </div>
        <div className="flex items-center gap-2 mt-1">
          <button
            type="button"
            onClick={onPickTemplate}
            className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft text-sm font-medium text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-[background-color,border-color,color,scale] duration-check ease-out active:scale-[0.97]"
          >
            Browse templates
          </button>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center h-8 px-3 rounded-md text-sm font-medium text-muted hover:text-ink transition-[color,scale] duration-check ease-out active:scale-[0.97]"
          >
            Start from scratch
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
      <AnimatePresence mode="popLayout" initial={false}>
        {automations.map((automation) => (
          <AutomationCard
            key={automation.task_id}
            automation={automation}
            onEdit={() => onEdit(automation)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}

function SystemList({ automations }: { automations: Automation[] | null }) {
  if (automations === null) {
    return <div className="text-sm text-muted">Loading…</div>;
  }
  if (automations.length === 0) {
    return (
      <div className="grid gap-2 max-w-[520px] py-10">
        <div className="text-md font-medium text-ink">No system automations.</div>
        <div className="text-sm text-muted leading-[1.5]">
          Knowledge reflection, retention, and health checks are seeded by the server when memory is enabled.
        </div>
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      <div className="text-sm text-muted leading-[1.5] max-w-[720px]">
        Background knowledge work is automatic. Power controls are limited to pause, run now, and inspect last result.
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
        <AnimatePresence mode="popLayout" initial={false}>
          {automations.map((automation) => (
            <AutomationCard
              key={automation.task_id}
              automation={automation}
              onEdit={() => undefined}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── Templates list ─────────────────────────────────────────────────

function TemplatesList({
  onPick,
  onPickSuggestion,
}: {
  onPick: (template: AutomationTemplate) => void;
  onPickSuggestion: (suggestion: AutomationSuggestion) => void;
}) {
  const groups = useMemo(() => templatesByCategory(), []);
  const suggestions = useStore((s) => s.automationSuggestions);
  return (
    <div className="grid gap-6 content-start">
      <SuggestionsSection suggestions={suggestions} onPick={onPickSuggestion} />
      {groups.map(({ category, items }) => (
        <section key={category} className="grid gap-2">
          <h3 className="m-0 text-xs font-medium uppercase tracking-[0.08em] text-muted">
            {category}
          </h3>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
            {items.map((template) => (
              <TemplateCard key={template.id} template={template} onPick={() => onPick(template)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

// ─── Suggested for you ──────────────────────────────────────────────

const SUGGESTION_ICONS: Record<string, LucideIcon> = {
  Sparkles,
  Bell,
  Briefcase,
  CalendarClock,
  Clock,
  FileSearch,
  FileText,
  GitPullRequest,
  Inbox,
  Mail,
};

function suggestionIcon(name: string | null): LucideIcon {
  return (name && SUGGESTION_ICONS[name]) || Sparkles;
}

/** Server-synthesized, contextual automation cards rendered above the
 *  static templates. Renders nothing when there are no active suggestions
 *  so cold-start shows only the static templates. */
export function SuggestionsSection({
  suggestions,
  onPick,
  onDismiss = dismissSuggestion,
}: {
  suggestions: AutomationSuggestion[] | null;
  onPick: (suggestion: AutomationSuggestion) => void;
  onDismiss?: (id: string) => void;
}) {
  // Suggestions resolve async after the templates paint. Rise the section in
  // only when it arrives late — on tab revisits the data is already loaded
  // and the section mounts statically with the rest of the panel.
  const arrivedLate = useRef(!suggestions || suggestions.length === 0);
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <motion.section
      initial={arrivedLate.current ? RISE_IN : false}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.panel, ease: EASE_DECELERATE }}
      className="grid gap-2"
    >
      <h3 className="m-0 text-xs font-medium uppercase tracking-[0.08em] text-muted">
        Suggested for you
      </h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
        <AnimatePresence mode="popLayout" initial={false}>
          {suggestions.map((suggestion) => (
            <SuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              onPick={onPick}
              onDismiss={onDismiss}
            />
          ))}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}

export function SuggestionCard({
  suggestion,
  onPick,
  onDismiss = dismissSuggestion,
}: {
  suggestion: AutomationSuggestion;
  onPick: (suggestion: AutomationSuggestion) => void;
  onDismiss?: (id: string) => void;
}) {
  const Icon = suggestionIcon(suggestion.icon);
  const schedule = suggestion.triggers.map(formatTrigger).join(" · ") || "—";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_LAYOUT}
      data-suggestion={suggestion.id}
      className="group/suggestion surface-panel surface-radius-sm relative grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left focus-within:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[scale] duration-check ease-out has-[button:active]:scale-[0.99]"
    >
      {/* Stretched accessible click target (see AutomationCard) — a real button
          over the card, below the dismiss control which is positioned above it. */}
      <button
        type="button"
        aria-label={`Use suggestion: ${suggestion.name}`}
        onClick={() => onPick(suggestion)}
        className="absolute inset-0 cursor-pointer rounded-[inherit] focus:outline-none"
      />
      <Icon size={ICON.SM} strokeWidth={2} className="text-muted mt-[2px] shrink-0" />
      <div className="relative z-[1] min-w-0 grid gap-1.5 pr-6">
        <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
          {suggestion.name}
        </h4>
        <ShowMore collapsedHeight={44} moreLabel="More" lessLabel="Less">
          <p className="m-0 text-sm text-muted leading-[1.5]">{suggestion.rationale}</p>
        </ShowMore>
        <Badge tone="neutral" className="font-mono tabular-nums" title={schedule}>
          {schedule}
        </Badge>
      </div>
      <Tooltip label="Dismiss">
        <button
          type="button"
          aria-label="Dismiss suggestion"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(suggestion.id);
          }}
          className="absolute top-2.5 right-2.5 z-[1] grid h-6 w-6 place-items-center rounded-md text-faint opacity-0 transition-opacity hover:bg-surface-soft hover:text-ink group-hover/suggestion:opacity-100 focus-visible:opacity-100 focus-visible:outline-none"
        >
          <X size={ICON.XS} strokeWidth={2} />
        </button>
      </Tooltip>
    </motion.div>
  );
}

// ─── Card: existing automation ──────────────────────────────────────

function _runDuration(start: string, end: string): string {
  const ms = Date.parse(end) - Date.parse(start);
  if (!Number.isFinite(ms) || ms < 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m}m` : `${Math.round(m / 60)}h`;
}

/** Recent runs as a markdown digest, shown in the existing markdown viewer. */
function formatRunsMarkdown(runs: AutomationRun[]): string {
  if (runs.length === 0) return "_No runs recorded yet._";
  return runs
    .map((r) => {
      const mark = r.status === "completed" ? "✓" : r.status === "failed" ? "✗" : "•";
      const dur = r.ended_at ? _runDuration(r.started_at, r.ended_at) : "running";
      const head = `**${mark} ${formatRelative(r.started_at)}** · ${r.status}${dur ? ` · ${dur}` : ""}`;
      const detail = (r.error ?? r.result ?? "").trim();
      const quoted = detail
        ? "\n" + detail.split("\n").slice(0, 6).map((l) => `> ${l}`).join("\n")
        : "";
      return head + quoted;
    })
    .join("\n\n");
}

/** The enable/pause toggle that occupies the leading glyph footprint — the
 *  ONE always-visible control on an automation card (the agent Bot glyph's
 *  counterpart). Forced muted, never green, so it reads as a control, not a
 *  status; paused-ness is conveyed by the hollow ring + the "paused" meta. */
function AutomationToggle({
  enabled,
  busy,
  onToggle,
}: {
  enabled: boolean;
  busy: boolean;
  onToggle: (e: React.MouseEvent) => void;
}) {
  return (
    <span
      className="relative z-[1] grid place-items-center shrink-0 self-center"
      style={{ width: ICON.MD, height: ICON.MD }}
    >
      <Tooltip label={enabled ? "Pause" : "Enable"}>
        <button
          type="button"
          onClick={onToggle}
          disabled={busy}
          aria-label={enabled ? "Pause automation" : "Enable automation"}
          className={clsx(
            "grid place-items-center w-[10px] h-[10px] rounded-full transition-colors",
            enabled
              ? "bg-ink-soft hover:bg-ink"
              : "bg-transparent border border-line-strong hover:border-muted",
            busy && "opacity-50",
          )}
        />
      </Tooltip>
    </span>
  );
}

function AutomationCard({
  automation,
  onEdit,
}: {
  automation: Automation;
  onEdit: () => void;
}) {
  const config = useStore((s) => s.config);
  const [busy, setBusy] = useState<"toggle" | "run" | "delete" | null>(null);

  const wrap = (action: typeof busy, fn: () => Promise<void>) => async () => {
    if (busy) return;
    setBusy(action);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!confirm(`Delete "${automation.name}"?`)) return;
    setBusy("delete");
    try {
      await deleteAutomation(automation.task_id);
    } finally {
      setBusy(null);
    }
  };

  const running = automation.running_since != null;
  const hasResult = !!automation.last_result?.trim();
  const setMarkdownView = useStore((s) => s.setViewingMarkdown);
  const showRunHistory = async () => {
    const runs = await listAutomationRunsApi(config, automation.task_id, 30);
    setMarkdownView({
      title: automation.name || "Automation",
      subtitle: "run history",
      content: formatRunsMarkdown(runs),
    });
  };
  const sessions = useStore((s) => s.sessions);
  const closeAutomations = useStore((s) => s.closeAutomations);
  const channel = sessions.find((sx) => sx.origin_automation_id === automation.task_id) ?? null;
  const trustLabel = automationTrustLabel(automation);
  const editable = !automation.builtin;

  // The card's primary navigation: editable → open the editor; otherwise an
  // automation with a bound channel → open that channel; otherwise inert.
  const openChannel = channel
    ? () => {
        void switchSession(channel.session_id);
        closeAutomations();
      }
    : undefined;
  const open = editable ? onEdit : openChannel;

  // One agent view-model, the same body. Automation runs aren't openable
  // sessions, so the view's childSessionId is intentionally unset — the card
  // wires its own open handler above.
  const run = agentRunFromAutomation(automation);

  // Per-instance affordances — NOT the hardcoded agent set. Builtins lose
  // delete + click-to-edit; channel automations gain "Open channel".
  const actions: AgentRunAction[] = [
    {
      icon: Play,
      label: "Run now",
      onClick: wrap("run", () => runAutomation(automation.task_id)),
      busy: busy === "run",
      disabled: !automation.enabled || running,
    },
    { icon: History, label: "Run history", onClick: () => showRunHistory() },
    ...(hasResult
      ? [
          {
            icon: FileText,
            label: "View last run",
            onClick: () =>
              setMarkdownView({
                title: automation.name || "Automation",
                subtitle: automation.last_run_at
                  ? `last run ${formatRelative(automation.last_run_at)}`
                  : undefined,
                content: automation.last_result ?? "",
              }),
          } satisfies AgentRunAction,
        ]
      : []),
    ...(channel
      ? [{ icon: Radio, label: "Open channel", onClick: openChannel! } satisfies AgentRunAction]
      : []),
    ...(!automation.builtin
      ? [
          {
            icon: Trash2,
            label: "Delete",
            onClick: remove,
            busy: busy === "delete",
            danger: true,
          } satisfies AgentRunAction,
        ]
      : []),
  ];

  const badges =
    running || trustLabel || isChannelAutomation(automation) ? (
      <>
        {running && (
          <Badge tone="accent" leading={<Circle size={5} strokeWidth={3} fill="currentColor" />}>
            running
          </Badge>
        )}
        {isChannelAutomation(automation) && (
          <Badge tone="neutral" leading={<Radio size={9} strokeWidth={2.2} />}>
            channel
          </Badge>
        )}
        {trustLabel && <Badge tone={automationTrustTone(automation)}>{trustLabel}</Badge>}
      </>
    ) : null;

  const interactive = !!open;
  const openLabel = editable
    ? `Edit ${automation.name || "automation"}`
    : `Open ${automation.name || "automation"} channel`;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_LAYOUT}
      className={clsx(
        "group/run surface-panel surface-radius-sm relative grid content-start gap-1.5 p-3.5 overflow-hidden focus-within:shadow-[0_0_0_3px_var(--color-accent-soft)]",
        interactive && "transition-[scale] duration-check ease-out has-[>button:active]:scale-[0.99]",
      )}
    >
      {/* Stretched, accessible click target: a real <button> over the whole card
          (keyboard + screen-reader friendly), painted BELOW the toggle and the
          hover-actions — which are positioned above it (z-[1] / absolute) so each
          stays independently clickable. Replaces the old article[role="button"]
          that illegally nested interactive buttons inside a button. */}
      {interactive && (
        <button
          type="button"
          aria-label={openLabel}
          onClick={open}
          className="absolute inset-0 cursor-pointer rounded-[inherit] focus:outline-none"
        />
      )}
      <AgentRunContent
        run={run}
        actions={actions}
        leading={
          <AutomationToggle
            enabled={automation.enabled}
            busy={busy === "toggle"}
            onToggle={(e) => {
              e.stopPropagation();
              void wrap("toggle", () => toggleAutomation(automation.task_id))();
            }}
          />
        }
        badges={badges}
      />
      <p className="relative z-[1] self-start pl-[24px] m-0 min-w-0 max-w-full text-sm text-muted leading-[1.5] line-clamp-2 [overflow-wrap:anywhere]">
        {automation.description || "No description."}
      </p>
    </motion.article>
  );
}

// ─── Template card ──────────────────────────────────────────────────

function TemplateCard({
  template,
  onPick,
}: {
  template: AutomationTemplate;
  onPick: () => void;
}) {
  const Icon = template.icon;
  return (
    <button
      type="button"
      onClick={onPick}
      className="surface-panel surface-radius-sm focus-ring-accent cursor-pointer grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left transition-[scale] duration-check ease-out active:scale-[0.99]"
    >
      <Icon size={ICON.SM} strokeWidth={2} className="text-muted mt-[2px] shrink-0" />
      <div className="min-w-0 grid gap-1">
        <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
          {template.name}
        </h4>
        <p className="m-0 text-sm text-muted leading-[1.5] line-clamp-2">
          {template.blurb}
        </p>
      </div>
    </button>
  );
}

