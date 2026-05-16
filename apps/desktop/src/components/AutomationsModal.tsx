import { useEffect, useMemo, useState } from "react";
import { Circle, FileText, Play, Plus, Radio, Trash2, type LucideIcon } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { deleteAutomation, fetchAutomations, runAutomation, toggleAutomation } from "../actions";
import type { Automation, AutomationTrigger } from "../api";
import { isChannelAutomation, splitAutomationsForTabs } from "../lib/automationFilters";
import { automationTrustLabel, automationTrustTone } from "../lib/automationTrust";
import { AutomationEditor, type EditorSeed } from "./automations/AutomationEditor";
import { templatesByCategory, type AutomationTemplate } from "./automations/templates";
import { PageModal } from "./PageModal";
import { ICON } from "../lib/icons";

type Tab = "active" | "channels" | "internal" | "templates";

export function AutomationsModal() {
  const open = useStore((s) => s.automationsOpen);
  const close = useStore((s) => s.closeAutomations);
  const automations = useStore((s) => s.automations);
  const [editor, setEditor] = useState<EditorSeed | null>(null);
  const [tab, setTab] = useState<Tab>("active");

  useEffect(() => {
    if (!open) return;
    void fetchAutomations();
  }, [open]);

  // When the user has nothing yet, default the page to Templates so the
  // empty Active tab doesn't feel like a dead end.
  useEffect(() => {
    if (!open) return;
    if (automations !== null && automations.length === 0) setTab("templates");
  }, [open, automations]);

  const automationGroups = useMemo(() => (automations ? splitAutomationsForTabs(automations) : null), [automations]);
  const activeCount = automationGroups?.user.length ?? 0;
  const internalCount = automationGroups?.internal.length ?? 0;
  const channelCount = automationGroups?.channels.length ?? 0;

  return (
    <>
      <PageModal
        open={open}
        onClose={close}
        grid="grid-rows-[auto_auto_minmax(0,1fr)]"
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
        <nav className="flex items-center gap-5 px-6 border-b border-line-soft">
          <TabButton label="Active" count={activeCount} active={tab === "active"} onClick={() => setTab("active")} />
          <TabButton
            label="Channels"
            count={channelCount}
            active={tab === "channels"}
            onClick={() => setTab("channels")}
          />
          <TabButton
            label="Internal"
            count={internalCount}
            active={tab === "internal"}
            onClick={() => setTab("internal")}
          />
          <TabButton label="Templates" active={tab === "templates"} onClick={() => setTab("templates")} />
        </nav>

        <div className="overflow-y-auto scroll-thin px-6 py-5">
          {tab === "active" ? (
            <ActiveList
              automations={automationGroups?.user ?? null}
              onEdit={(automation) => setEditor({ kind: "edit", automation })}
              onPickTemplate={() => setTab("templates")}
              onCreate={() => setEditor({ kind: "create" })}
            />
          ) : tab === "channels" ? (
            <ChannelList automations={automationGroups?.channels ?? null} />
          ) : tab === "internal" ? (
            <InternalList automations={automationGroups?.internal ?? null} />
          ) : (
            <TemplatesList
              onPick={(template) => setEditor({ kind: "create", preset: template.payload })}
            />
          )}
        </div>
      </PageModal>
      <AutomationEditor seed={editor} onClose={() => setEditor(null)} />
    </>
  );
}

function TabButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "relative inline-flex items-center gap-1.5 h-9 text-base font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {count != null && count > 0 && (
        <span
          className={clsx(
            "inline-flex items-center justify-center min-w-[20px] h-[18px] px-1.5 rounded-full text-2xs font-medium tabular-nums",
            active ? "bg-ink text-on-ink" : "bg-surface-soft text-muted",
          )}
        >
          {count}
        </span>
      )}
      {active && (
        <span className="absolute left-0 right-0 -bottom-px h-[2px] bg-ink rounded-full" />
      )}
    </button>
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
    return <div className="text-sm text-faint">Loading…</div>;
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
      {automations.map((automation) => (
        <AutomationCard
          key={automation.task_id}
          automation={automation}
          onEdit={() => onEdit(automation)}
        />
      ))}
    </div>
  );
}

function ChannelList({ automations }: { automations: Automation[] | null }) {
  if (automations === null) {
    return <div className="text-sm text-faint">Loading…</div>;
  }
  if (automations.length === 0) {
    return (
      <div className="grid gap-2 max-w-[420px] py-10">
        <div className="text-md font-medium text-ink">No channels yet.</div>
        <div className="text-sm text-muted leading-[1.5]">
          Channels are post-mode loops that emit to a dedicated session each
          tick. Ask the agent to set one up — e.g. "every morning post a brief
          to a new session".
        </div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
      {automations.map((automation) => (
        <AutomationCard
          key={automation.task_id}
          automation={automation}
          onEdit={() => undefined}
        />
      ))}
    </div>
  );
}

function InternalList({ automations }: { automations: Automation[] | null }) {
  if (automations === null) {
    return <div className="text-sm text-faint">Loading…</div>;
  }
  if (automations.length === 0) {
    return (
      <div className="grid gap-2 max-w-[420px] py-10">
        <div className="text-md font-medium text-ink">No internal automations.</div>
        <div className="text-sm text-muted leading-[1.5]">
          Internal memory maintenance tasks will appear here when available.
        </div>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5">
      {automations.map((automation) => (
        <AutomationCard
          key={automation.task_id}
          automation={automation}
          onEdit={() => undefined}
        />
      ))}
    </div>
  );
}

// ─── Templates list ─────────────────────────────────────────────────

function TemplatesList({ onPick }: { onPick: (template: AutomationTemplate) => void }) {
  const groups = useMemo(() => templatesByCategory(), []);
  return (
    <div className="grid gap-6 content-start">
      {groups.map(({ category, items }) => (
        <section key={category} className="grid gap-2">
          <h3 className="m-0 text-xs font-medium uppercase tracking-[0.08em] text-faint">
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

// ─── Card: existing automation ──────────────────────────────────────

function AutomationCard({
  automation,
  onEdit,
}: {
  automation: Automation;
  onEdit: () => void;
}) {
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
  const setMarkdownView = useStore((s) => s.setViewingMarkdown);
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
    <article
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
        "group/auto-card glass-surface glass-frosted glass-radius-sm relative grid gap-2 p-3.5 rounded-[10px] focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--color-accent-soft)]",
        editable && "cursor-pointer",
      )}
    >
      <div className="grid grid-cols-[10px_minmax(0,1fr)] items-start gap-2.5 min-w-0">
        <button
          type="button"
          onClick={stop(wrap("toggle", () => toggleAutomation(automation.task_id)))}
          disabled={busy === "toggle"}
          title={automation.enabled ? "Pause" : "Enable"}
          aria-label={automation.enabled ? "Pause automation" : "Enable automation"}
          className={clsx(
            "mt-[5px] grid place-items-center w-[10px] h-[10px] rounded-full transition-colors",
            automation.enabled
              ? "bg-ok"
              : "bg-transparent border border-line-strong hover:border-muted",
            busy === "toggle" && "opacity-50",
          )}
        />
        <div className="min-w-0 grid gap-1.5 pr-16">
          <div className="grid gap-1.5 min-w-0">
            <h4 className="m-0 text-base font-medium tracking-[-0.005em] text-ink truncate">
              {automation.name || "Untitled"}
            </h4>
            {(running || automation.builtin || trustLabel || isChannelAutomation(automation)) && (
              <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                {running && (
                  <Tag tone="accent">
                    <Circle size={5} strokeWidth={3} fill="currentColor" />
                    running
                  </Tag>
                )}
                {isChannelAutomation(automation) && (
                  <Tag tone="neutral">
                    <Radio size={9} strokeWidth={2.2} />
                    channel
                  </Tag>
                )}
                {automation.builtin && <Tag tone="neutral">builtin</Tag>}
                {trustLabel && <Tag tone={automationTrustTone(automation)}>{trustLabel}</Tag>}
              </div>
            )}
          </div>
          <p className="m-0 text-sm text-muted leading-[1.5] line-clamp-2">
            {automation.description || "No description."}
          </p>
        </div>
        <div className="absolute top-2.5 right-2.5 flex items-center gap-px opacity-0 group-hover/auto-card:opacity-100 focus-within:opacity-100 transition-opacity">
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

      <div className="grid gap-1 pl-[19px] text-xs font-mono tabular-nums text-faint">
        <span className="min-w-0 truncate" title={trigger}>{trigger}</span>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {(() => {
          const nextLabel = formatNext(automation);
          return nextLabel ? (
            <span title={automation.next_run_at ?? undefined}>{nextLabel}</span>
          ) : null;
        })()}
        {hasResult && automation.last_run_at && (
            <button
              type="button"
              onClick={stop(() =>
                setMarkdownView({
                  title: automation.name || "Automation",
                  subtitle: `last run ${formatRelative(automation.last_run_at!)}`,
                  content: automation.last_result ?? "",
                }),
              )}
              className="font-mono tabular-nums text-faint hover:text-ink-soft underline-offset-2 hover:underline transition-colors"
              title="View last run"
            >
              ran {formatRelative(automation.last_run_at)}
            </button>
        )}
        </div>
      </div>
    </article>
  );
}

function Tag({
  tone,
  children,
}: {
  tone: "neutral" | "accent" | "bad";
  children: React.ReactNode;
}) {
  return (
    <span
      className={clsx(
        "inline-flex max-w-full shrink-0 items-center gap-1 px-1.5 h-[18px] rounded-full text-2xs font-medium tracking-[0.005em] whitespace-nowrap",
        tone === "accent" && "bg-accent-soft text-accent-strong",
        tone === "neutral" && "bg-surface-sunken text-muted",
        tone === "bad" && "bg-bad-soft text-bad",
      )}
    >
      {children}
    </span>
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
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      aria-label={label}
      title={label}
      className={clsx(
        "grid place-items-center w-6 h-6 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-30 disabled:cursor-not-allowed",
        danger && "hover:!text-bad",
      )}
    >
      <Icon size={ICON.XS} strokeWidth={2} />
    </button>
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
      className="glass-surface glass-frosted glass-radius-sm cursor-pointer grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 p-3.5 rounded-[10px] text-left focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--color-accent-soft)]"
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
  if (t.type === "count") return `count ${t.threshold ?? "?"}`;
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
