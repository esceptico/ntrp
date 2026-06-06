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
  Loader2,
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
import { SPRING_LAYOUT } from "../lib/tokens/motion";
import { useStore } from "../store";
import {
  deleteAutomation,
  dismissSuggestion,
  fetchAutomations,
  fetchAutomationSuggestions,
  runAutomation,
  switchSession,
  toggleAutomation,
} from "../actions";
import {
  listAutomationRunsApi,
  suggestionToPayload,
  type Automation,
  type AutomationRun,
  type AutomationSuggestion,
  type AutomationTrigger,
} from "../api";
import { isChannelAutomation, splitAutomationsForTabs } from "../lib/automationFilters";
import { automationTrustLabel, automationTrustTone } from "../lib/automationTrust";
import { AutomationEditor, type EditorSeed } from "./automations/AutomationEditor";
import { templatesByCategory, type AutomationTemplate } from "./automations/templates";
import { Badge } from "./Badge";
import { PageModal } from "./PageModal";
import { ICON } from "../lib/icons";
import { IconButton } from "./IconButton";
import { BlurSwap } from "./BlurSwap";
import { StatusDot } from "./StatusDot";
import { ScrollFadeTop } from "./ScrollBlur";
import { Tab as TabItem, Tabs } from "./ui/Tabs";
import { TabPanels, useTabDirection } from "./ui/TabPanels";

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
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity"
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
            className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft text-sm font-medium text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
          >
            Browse templates
          </button>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center h-8 px-3 rounded-md text-sm font-medium text-muted hover:text-ink transition-colors"
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
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <section className="grid gap-2">
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
    </section>
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
      exit={{ opacity: 0, scale: 0.97 }}
      transition={SPRING_LAYOUT}
      data-suggestion={suggestion.id}
      role="button"
      tabIndex={0}
      onClick={() => onPick(suggestion)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick(suggestion);
        }
      }}
      className="group/suggestion surface-panel surface-radius-sm relative grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--color-accent-soft)]"
    >
      <Icon size={ICON.SM} strokeWidth={2} className="text-muted mt-[2px] shrink-0" />
      <div className="min-w-0 grid gap-1.5 pr-6">
        <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
          {suggestion.name}
        </h4>
        <p className="m-0 text-sm text-muted leading-[1.5] line-clamp-2">
          {suggestion.rationale}
        </p>
        <Badge tone="neutral" className="font-mono tabular-nums" title={schedule}>
          {schedule}
        </Badge>
      </div>
      <button
        type="button"
        aria-label="Dismiss suggestion"
        title="Dismiss"
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(suggestion.id);
        }}
        className="absolute top-2.5 right-2.5 grid h-6 w-6 place-items-center rounded-md text-faint opacity-0 transition-opacity hover:bg-surface-soft hover:text-ink group-hover/suggestion:opacity-100 focus-visible:opacity-100 focus-visible:outline-none"
      >
        <X size={ICON.XS} strokeWidth={2} />
      </button>
    </motion.div>
  );
}

// ─── Card: existing automation ──────────────────────────────────────

/** Tailwind bg for a run-status sparkline dot. */
function sparkTone(status: string): string {
  return status === "completed"
    ? "bg-ok"
    : status === "failed"
      ? "bg-bad"
      : status === "running"
        ? "bg-accent"
        : "bg-muted";
}

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
  const trigger = automation.triggers.map(formatTrigger).join(" · ") || "—";
  const hasResult = !!automation.last_result?.trim();
  const recentStatuses = automation.recent_statuses ?? [];
  const lastStatus = automation.last_status ?? null;
  // Rail color encodes state at a glance. Precedence: running > failed > on > paused.
  const railTone = running
    ? "bg-accent"
    : lastStatus === "failed"
      ? "bg-bad"
      : automation.enabled
        ? "bg-ok"
        : "bg-line-strong";
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
  const open = () => {
    if (editable) onEdit();
  };
  // Stop a click that originated from a nested action button from also
  // triggering the card-level "open editor" navigation.
  const stop = (handler: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    handler();
  };

  return (
    <motion.article
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={SPRING_LAYOUT}
      role={editable ? "button" : undefined}
      tabIndex={editable ? 0 : -1}
      onClick={editable ? open : undefined}
      onKeyDown={(e) => {
        if (!editable) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      className={clsx(
        "group/auto-card surface-panel surface-radius-sm relative grid grid-cols-[4px_minmax(0,1fr)] overflow-hidden focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--color-accent-soft)]",
        editable && "cursor-pointer",
      )}
    >
      {/* Status rail — color-codes state at a glance (running > failed > on >
          paused) and is the enable/pause toggle. */}
      <button
        type="button"
        onClick={stop(wrap("toggle", () => toggleAutomation(automation.task_id)))}
        disabled={busy === "toggle"}
        title={automation.enabled ? "Pause" : "Enable"}
        aria-label={automation.enabled ? "Pause automation" : "Enable automation"}
        className={clsx(
          "h-full w-full transition-colors duration-panel hover:opacity-80",
          railTone,
          running && "status-dot-breathe",
          busy === "toggle" && "opacity-50",
        )}
      />

      <div className="grid gap-2 py-3 pl-3 pr-3 min-w-0">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2.5 min-w-0">
          <div className="min-w-0 grid gap-1.5">
            <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
              {automation.name || "Untitled"}
            </h4>
            {(running || trustLabel || isChannelAutomation(automation)) && (
              <div className="flex flex-wrap items-center gap-1.5 min-w-0">
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
              </div>
            )}
            <p className="m-0 text-sm text-muted leading-[1.5] line-clamp-2">
              {automation.description || "No description."}
            </p>
          </div>
          <div className="flex items-center gap-px self-start -mt-0.5 opacity-0 group-hover/auto-card:opacity-100 focus-within:opacity-100 transition-opacity duration-row ease-out">
            {channel && (
              <CardAction
                icon={Radio}
                label="Open channel"
                onClick={stop(() => {
                  void switchSession(channel.session_id);
                  closeAutomations();
                })}
              />
            )}
            {hasResult && (
              <CardAction
                icon={FileText}
                label="View last run"
                onClick={stop(() =>
                  setMarkdownView({
                    title: automation.name || "Automation",
                    subtitle: automation.last_run_at
                      ? `last run ${formatRelative(automation.last_run_at)}`
                      : undefined,
                    content: automation.last_result ?? "",
                  }),
                )}
              />
            )}
            <CardAction icon={History} label="Run history" onClick={stop(() => void showRunHistory())} />
            <CardAction
              icon={Play}
              label="Run now"
              onClick={stop(wrap("run", () => runAutomation(automation.task_id)))}
              busy={busy === "run"}
              disabled={!automation.enabled}
            />
            <CardAction
              icon={Trash2}
              label="Delete"
              onClick={stop(remove)}
              busy={busy === "delete"}
              disabled={automation.builtin}
              danger
            />
          </div>
        </div>

        {/* schedule (left) · outcome sparkline + last-status pip (right) */}
        <div className="flex items-center justify-between gap-3 text-xs font-mono tabular-nums text-faint min-w-0">
          <span className="min-w-0 truncate" title={trigger}>
            {[trigger, formatNext(automation)].filter(Boolean).join(" · ")}
          </span>
          <div className="shrink-0 flex items-center gap-2">
            {recentStatuses.length > 0 && (
              <button
                type="button"
                onClick={stop(() => void showRunHistory())}
                title="Run history"
                aria-label="Run history"
                className="inline-flex items-center gap-0.5 hover:opacity-80 transition-opacity"
              >
                {recentStatuses.slice(0, 4).reverse().map((s, i) => (
                  <span key={i} className={clsx("w-1 h-1 rounded-[1px]", sparkTone(s))} />
                ))}
              </button>
            )}
            {lastStatus ? (
              <button
                type="button"
                onClick={stop(() =>
                  hasResult
                    ? setMarkdownView({
                        title: automation.name || "Automation",
                        subtitle: automation.last_run_at
                          ? `last run ${formatRelative(automation.last_run_at)}`
                          : undefined,
                        content: automation.last_result ?? "",
                      })
                    : void showRunHistory(),
                )}
                title={hasResult ? "View last run" : "Run history"}
                className={clsx(
                  "inline-flex items-center gap-1 transition-colors hover:text-ink-soft",
                  lastStatus === "failed" && "text-bad",
                )}
              >
                <StatusDot
                  status={lastStatus as "completed" | "failed" | "running"}
                  pulse={lastStatus === "running"}
                />
                <span>
                  {lastStatus === "running"
                    ? "running"
                    : lastStatus === "failed"
                      ? `failed${automation.last_run_at ? ` ${formatRelative(automation.last_run_at)}` : ""}`
                      : automation.last_run_at
                        ? formatRelative(automation.last_run_at)
                        : "done"}
                </span>
              </button>
            ) : (
              automation.last_run_at && (
                <button
                  type="button"
                  onClick={stop(() =>
                    hasResult
                      ? setMarkdownView({
                          title: automation.name || "Automation",
                          subtitle: `last run ${formatRelative(automation.last_run_at!)}`,
                          content: automation.last_result ?? "",
                        })
                      : void showRunHistory(),
                  )}
                  className="hover:text-ink-soft transition-colors"
                  title={hasResult ? "View last run" : "Run history"}
                >
                  ran {formatRelative(automation.last_run_at)}
                </button>
              )
            )}
          </div>
        </div>
      </div>
    </motion.article>
  );
}

function CardAction({
  icon: Icon,
  label,
  onClick,
  disabled,
  busy,
  danger,
}: {
  icon: LucideIcon;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  disabled?: boolean;
  busy?: boolean;
  danger?: boolean;
}) {
  return (
    <IconButton
      size="sm"
      tone="faint"
      danger={danger}
      onClick={onClick}
      disabled={disabled || busy}
      aria-label={label}
      title={label}
    >
      <BlurSwap swapKey={busy ? "busy" : "idle"} blur={3}>
        {busy ? (
          <Loader2 size={ICON.XS} strokeWidth={2} className="animate-spin" />
        ) : (
          <Icon size={ICON.XS} strokeWidth={2} />
        )}
      </BlurSwap>
    </IconButton>
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
      className="surface-panel surface-radius-sm cursor-pointer grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 text-left focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--color-accent-soft)]"
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

// ─── helpers ────────────────────────────────────────────────────────

function formatTrigger(t: AutomationTrigger): string {
  if (t.type === "time") {
    if (t.every) {
      const win = t.start && t.end ? ` ${t.start}–${t.end}` : "";
      const days = t.days ? ` · ${t.days}` : "";
      return `every ${t.every}${win}${days}`;
    }
    if (t.at) {
      const days = t.days ? ` · ${t.days}` : "";
      return `at ${t.at}${days}`;
    }
    return "time";
  }
  if (t.type === "event") {
    const lead = t.lead_minutes != null ? ` (${t.lead_minutes}m)` : "";
    return `on:${t.event_type ?? "?"}${lead}`;
  }
  if (t.type === "idle") return `idle ${t.idle_minutes}m`;
  if (t.type === "count") return `every ${t.every_n ?? t.threshold ?? "?"} turns`;
  return t.type;
}

/** Build a human label for the "next run" slot on the card. Skips the
 *  slot for paused automations and avoids the "next 36d ago" oddity when
 *  the scheduler hasn't yet recomputed a next-run timestamp. */
function formatNext(automation: Automation): string | null {
  if (!automation.enabled) return "paused";
  if (!automation.next_run_at) return null;
  const t = new Date(automation.next_run_at).getTime();
  if (!Number.isFinite(t)) return null;
  if (t <= Date.now()) return "due now";
  return `next ${formatRelative(automation.next_run_at)}`;
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return iso;
  const delta = then - Date.now();
  const abs = Math.abs(delta);
  const min = Math.round(abs / 60_000);
  if (min < 1) return delta > 0 ? "<1m" : "now";
  if (min < 60) return delta > 0 ? `in ${min}m` : `${min}m ago`;
  const h = Math.round(min / 60);
  if (h < 24) return delta > 0 ? `in ${h}h` : `${h}h ago`;
  const d = Math.round(h / 24);
  return delta > 0 ? `in ${d}d` : `${d}d ago`;
}
