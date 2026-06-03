import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { useStore } from "../../store";
import { DURATION_POPOVER, EASE_DECELERATE } from "../../lib/tokens/motion";

/** Compact "two scales on one ring" budget meter. Outer arc = token
 *  pressure (parent context only — subagent internals don't count, per
 *  the compactor logic). Inner arc = message pressure. Token pressure
 *  near the configured limit or message pressure at the cap triggers
 *  auto-compaction on the server. Hover or click for the
 *  breakdown. */

const SIZE = 18;
const STROKE = 2.2;
const OUTER_R = SIZE / 2 - STROKE / 2 - 0.5;
const INNER_R = OUTER_R - STROKE - 1.2;
const OUTER_C = 2 * Math.PI * OUTER_R;
const INNER_C = 2 * Math.PI * INNER_R;

function ratioColor(ratio: number): string {
  if (ratio >= 0.9) return "var(--color-bad)";
  if (ratio >= 0.7) return "var(--color-warn)";
  return "var(--color-ink-soft)";
}

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  if (n === 0) return "$0";
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}

function formatPct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export function BudgetDial() {
  const usage = useStore((s) => s.usage);
  const serverConfig = useStore((s) => s.serverConfig);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ bottom: number; right: number }>({
    bottom: 0,
    right: 0,
  });
  const hideTimerRef = useRef<number | null>(null);

  const modelCeiling = serverConfig?.chat_model_max_context ?? 0;
  const compressionPct = serverConfig
    ? Math.round(serverConfig.compression_threshold * 100)
    : 80;
  const tokenLimit =
    serverConfig?.compaction_token_limit
      ?? (modelCeiling > 0 ? Math.floor(modelCeiling * 0.8) : 0);
  const tokenTrigger = serverConfig?.compaction_token_trigger ?? 0;
  const messageLimit = serverConfig?.max_messages ?? 0;
  const tokenRatio = tokenLimit > 0 ? Math.min(1, usage.lastPrompt / tokenLimit) : 0;
  const messageRatio = messageLimit > 0 ? Math.min(1, usage.messageCount / messageLimit) : 0;
  const maxRatio = Math.max(tokenRatio, messageRatio);
  const hasAnyData = usage.lastPrompt > 0 || usage.messageCount > 0 || usage.totalCost > 0;

  const cancelHide = () => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  };
  const show = () => {
    cancelHide();
    setOpen(true);
  };
  const scheduleHide = () => {
    cancelHide();
    // 200ms — generous bridge for the 8px gap so the user can move from
    // trigger to popover without the popover snapping shut. LoopStatus
    // uses the same shape with 80ms; bumped here because the dial sits
    // close to the composer's right edge and the popover renders to its
    // left, so the cursor has to travel further across that gap.
    hideTimerRef.current = window.setTimeout(() => setOpen(false), 200);
  };
  const toggle = () => setOpen((v) => !v);

  // useLayoutEffect so coords are committed before the popover paints —
  // an open=true / coords-still-zero frame would render the popover at
  // the top-left of the viewport for one tick (visible flash).
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      setCoords({
        bottom: Math.max(8, window.innerHeight - r.top + 8),
        right: Math.max(8, window.innerWidth - r.right - 8),
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  // Click-outside to close. Cheap insurance for the case where hover
  // misbehaves on a flaky trackpad and the popover gets stuck open.
  useLayoutEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  // Visible compact label: prefer cost when present (most useful at a
  // glance), else the last prompt's tokens, else a tiny "—" placeholder
  // so the dial always has a hover target with text in it.
  const compactLabel = usage.totalCost > 0
    ? formatCost(usage.totalCost)
    : usage.lastPrompt > 0
      ? `${formatTokens(usage.lastPrompt)}`
      : "—";

  return (
    <span className="inline-flex items-center">
      <button
        ref={triggerRef}
        type="button"
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onFocus={show}
        onBlur={scheduleHide}
        onClick={toggle}
        aria-label="Context budget"
        aria-expanded={open}
        title={
          hasAnyData
            ? `${formatTokens(usage.lastPrompt)} / ${formatTokens(tokenLimit)} tokens · ${usage.messageCount} / ${messageLimit} msgs`
            : "Context budget"
        }
        className={clsx(
          "inline-flex items-center gap-1.5 h-7 px-2 rounded-full",
          "text-xs text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,transform] duration-check ease-out active:scale-[0.97]",
          open && "bg-surface-soft text-ink",
        )}
      >
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className={clsx("shrink-0", maxRatio >= 1 && "animate-pulse")}
          aria-hidden
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={OUTER_R}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.22}
            strokeWidth={STROKE}
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={INNER_R}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.22}
            strokeWidth={STROKE}
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={OUTER_R}
            fill="none"
            stroke={ratioColor(tokenRatio)}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={OUTER_C}
            strokeDashoffset={OUTER_C * (1 - tokenRatio)}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            style={{ transition: "stroke-dashoffset var(--duration-panel) ease-out, stroke var(--duration-panel) ease-out" }}
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={INNER_R}
            fill="none"
            stroke={ratioColor(messageRatio)}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={INNER_C}
            strokeDashoffset={INNER_C * (1 - messageRatio)}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            style={{ transition: "stroke-dashoffset var(--duration-panel) ease-out, stroke var(--duration-panel) ease-out" }}
          />
        </svg>
        <span className="tabular-nums tracking-[-0.005em]">{compactLabel}</span>
      </button>
      {createPortal(
        <AnimatePresence>
          {open && (
            <motion.div
              ref={popoverRef}
              onMouseEnter={cancelHide}
              onMouseLeave={scheduleHide}
              initial={{ opacity: 0, y: 4, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.98 }}
              transition={{ duration: DURATION_POPOVER, ease: EASE_DECELERATE }}
              style={{
                position: "fixed",
                bottom: coords.bottom,
                right: coords.right,
                zIndex: 60,
                transformOrigin: "bottom right",
              }}
              className="surface-panel surface-popover w-[300px] p-3 text-sm"
            >
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <span className="text-xs font-medium text-muted">Context budget</span>
                {serverConfig?.chat_model && (
                  <span
                    className="text-2xs text-faint truncate max-w-[170px]"
                    title={serverConfig.chat_model}
                  >
                    {serverConfig.chat_model}
                  </span>
                )}
              </div>
              <Row
                label="Tokens"
                value={`${formatTokens(usage.lastPrompt)} / ${formatTokens(tokenLimit)}`}
                hint={tokenLimit > 0 ? formatPct(tokenRatio) : "—"}
                color={ratioColor(tokenRatio)}
                detail={
                  modelCeiling > 0
                    ? `${formatTokens(modelCeiling)} ceiling · budget ${compressionPct}%`
                    : undefined
                }
              />
              <Row
                label="Messages"
                value={`${usage.messageCount} / ${messageLimit}`}
                hint={messageLimit > 0 ? formatPct(messageRatio) : "—"}
                color={ratioColor(messageRatio)}
              />
              <div className="mt-2 pt-2 border-t border-line-soft grid grid-cols-2 gap-y-1 gap-x-3">
                {/* Spend row hidden when zero — for OAuth-backed providers
                    (openai-codex, claude-pro, etc.) the server has no
                    pricing data and "$0" is misleading. The provider just
                    doesn't meter per-token from us. */}
                {usage.totalCost > 0 && (
                  <>
                    <span className="text-faint">Session spend</span>
                    <span className="tabular-nums text-ink-soft text-right">
                      {formatCost(usage.totalCost)}
                    </span>
                  </>
                )}
                {usage.totalTokens > 0 && (
                  <>
                    <span className="text-faint">Total tokens</span>
                    <span className="tabular-nums text-ink-soft text-right">
                      {formatTokens(usage.totalTokens)}
                    </span>
                  </>
                )}
              </div>
              <div className="mt-2 text-2xs text-faint leading-snug">
                Auto-compacts at {formatTokens(tokenTrigger)} tokens or when messages hit 100%. Tool-agent tokens count toward session totals, not context pressure.
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </span>
  );
}

function Row({
  label,
  value,
  hint,
  color,
  detail,
}: {
  label: string;
  value: string;
  hint: string;
  color: string;
  detail?: string;
}) {
  return (
    <div className="py-0.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-faint">
          <span
            aria-hidden
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: color }}
          />
          {label}
        </span>
        <span className="tabular-nums text-ink-soft">
          {value}{" "}
          <span className="text-faint">· {hint}</span>
        </span>
      </div>
      {detail && (
        <div className="pl-3 text-2xs text-faint tabular-nums">{detail}</div>
      )}
    </div>
  );
}
