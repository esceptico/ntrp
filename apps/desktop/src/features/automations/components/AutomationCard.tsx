import { useState } from "react";
import {
  Circle,
  FileText,
  History,
  Play,
  Radio,
  Trash2,
} from "lucide-react";
import clsx from "clsx";
import { useStore } from "@/stores";
import { switchSession } from "@/actions/sessions";
import { deleteAutomation, runAutomation, toggleAutomation } from "@/actions/automations";
import { listAutomationRunsApi } from "@/api/automations";
import type { Automation } from "@/api/types";
import { isChannelAutomation } from "@/lib/automationFilters";
import { automationTrustLabel, automationTrustTone } from "@/features/automations/lib/automationTrust";
import { agentRunFromAutomation, formatRelative } from "@/lib/agentRun";
import { formatRunsMarkdown } from "@/features/automations/lib/automationFormat";
import { AgentRunContent, type AgentRunAction } from "@/components/ui/AgentRunRow";
import { Badge } from "@/components/ui/Badge";
import { ICON } from "@/lib/icons";
import { Tooltip } from "@/components/ui/Tooltip";
import { SurfaceCard } from "@/components/ui/SurfaceCard";

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

export function AutomationCard({
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

  // The card's primary navigation is the editor — builtins included (their
  // schedule and pause are the user's dials; the editor locks the rest).
  const openChannel = channel
    ? () => {
        void switchSession(channel.session_id);
        closeAutomations();
      }
    : undefined;
  const open = onEdit;

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
            confirm: true,
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
  const openLabel = `Edit ${automation.name || "automation"}`;

  return (
    <SurfaceCard
      as="article"
      interactive={interactive}
      onClick={open}
      ariaLabel={openLabel}
      className="group/run grid content-start gap-1.5 p-3.5 overflow-hidden"
    >
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
    </SurfaceCard>
  );
}
