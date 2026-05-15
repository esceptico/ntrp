import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { useStore } from "../../store";
import { SPRING_SMOOTH } from "../../lib/motion";

/** Compact "two scales on one ring" budget meter. Outer arc = token
 *  pressure (parent context only — subagent internals don't count, per
 *  the compactor logic). Inner arc = message pressure. Either hitting
 *  100% triggers auto-compaction on the server. Hover for the breakdown.
 *
 *  Replaces the old UsageDisplay text pill. Renders nothing until the
 *  first run finishes (`messageCount > 0`) so a fresh session shows no
 *  decoration. */

const SIZE = 22;
const STROKE = 2.4;
const OUTER_R = SIZE / 2 - STROKE / 2 - 0.5;
const INNER_R = OUTER_R - STROKE - 1.4;
const OUTER_C = 2 * Math.PI * OUTER_R;
const INNER_C = 2 * Math.PI * INNER_R;

function ratioColor(ratio: number): string {
  // Single graduation: cool → amber → red. Used by both arcs so the eye
  // can compare them against the same scale. CSS vars keep it palette-
  // aware in light / dark themes.
  if (ratio >= 0.9) return "var(--color-bad, #b8442b)";
  if (ratio >= 0.7) return "var(--color-warn, #c98a2b)";
  return "var(--color-muted)";
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
  const lastCompaction = useStore((s) => s.lastCompaction);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ bottom: number; right: number } | null>(null);
  const hideTimerRef = useRef<number | null>(null);

  // Compaction fires at `compression_threshold * model.max_context_tokens`,
  // so the dial's "100%" matches the actual trigger — not the raw model
  // ceiling. Falls back gracefully when serverConfig hasn't loaded yet.
  const modelCeiling = serverConfig?.chat_model_max_context ?? 0;
  const compressionPct = serverConfig
    ? Math.round(serverConfig.compression_threshold * 100)
    : 80;
  const tokenLimit = modelCeiling > 0
    ? Math.floor(modelCeiling * (serverConfig?.compression_threshold ?? 0.8))
    : 0;
  const messageLimit = serverConfig?.max_messages ?? 0;
  const tokenRatio = tokenLimit > 0 ? Math.min(1, usage.lastPrompt / tokenLimit) : 0;
  const messageRatio = messageLimit > 0 ? Math.min(1, usage.messageCount / messageLimit) : 0;
  const maxRatio = Math.max(tokenRatio, messageRatio);

  const show = () => {
    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    setOpen(true);
  };
  const scheduleHide = () => {
    if (hideTimerRef.current) window.clearTimeout(hideTimerRef.current);
    hideTimerRef.current = window.setTimeout(() => setOpen(false), 80);
  };

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      // 8px gap above the trigger, right-anchored. With the dial near the
      // composer's right edge, anchoring by left would let the popover
      // overflow the chat. Anchoring by right keeps it on-screen.
      setCoords({
        bottom: window.innerHeight - r.top + 8,
        right: window.innerWidth - r.right - 8,
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

  return (
    <span className="inline-flex items-center">
      <button
        ref={triggerRef}
        type="button"
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onFocus={show}
        onBlur={scheduleHide}
        aria-label="Budget"
        className={clsx(
          "inline-flex items-center gap-1.5 h-7 px-1.5 rounded-full",
          "text-xs text-faint hover:bg-surface-soft hover:text-ink transition-colors",
        )}
      >
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className={clsx(maxRatio >= 1 && "animate-pulse")}
        >
          {/* Track (faint) — drawn for both arcs so an empty scale still
              shows a visible ring rather than a blank pixel. */}
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={OUTER_R}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.12}
            strokeWidth={STROKE}
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={INNER_R}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.12}
            strokeWidth={STROKE}
          />
          {/* Outer fill = tokens. Rotated -90° so progress starts at 12
              o'clock; dasharray trick paints `ratio` of the circumference. */}
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
            style={{ transition: "stroke-dashoffset 240ms ease-out, stroke 240ms ease-out" }}
          />
          {/* Inner fill = messages. */}
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
            style={{ transition: "stroke-dashoffset 240ms ease-out, stroke 240ms ease-out" }}
          />
        </svg>
        {usage.totalCost > 0 && (
          <span className="tabular-nums tracking-[-0.005em]">
            {formatCost(usage.totalCost)}
          </span>
        )}
      </button>
      <AnimatePresence>
        {open && coords && createPortal(
          <motion.div
            onMouseEnter={show}
            onMouseLeave={scheduleHide}
            initial={{ opacity: 0, y: 4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.98 }}
            transition={SPRING_SMOOTH}
            style={{ position: "fixed", bottom: coords.bottom, right: coords.right, zIndex: 60 }}
            className="glass-pane-thick w-[300px] rounded-[12px] p-3 text-sm"
          >
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium text-muted">Context budget</span>
              {serverConfig?.chat_model && (
                <span className="text-[11px] text-faint truncate" title={serverConfig.chat_model}>
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
                  ? `${formatTokens(modelCeiling)} ceiling · compact at ${compressionPct}%`
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
              <span className="text-faint">Session spend</span>
              <span className="tabular-nums text-ink-soft text-right">
                {formatCost(usage.totalCost)}
              </span>
              {usage.totalTokens > 0 && (
                <>
                  <span className="text-faint">Total tokens</span>
                  <span className="tabular-nums text-ink-soft text-right">
                    {formatTokens(usage.totalTokens)}
                  </span>
                </>
              )}
              {lastCompaction && (
                <>
                  <span className="text-faint">Last compaction</span>
                  <span className="tabular-nums text-ink-soft text-right">
                    {lastCompaction.before} → {lastCompaction.after} msgs
                  </span>
                </>
              )}
            </div>
            <div className="mt-2 text-[11px] text-faint leading-snug">
              Auto-compacts when either scale hits 100%. Subagent spend is
              rolled into the cost; their own tokens stay off this gauge.
            </div>
          </motion.div>,
          document.body,
        )}
      </AnimatePresence>
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
        <div className="pl-3 text-[11px] text-faint tabular-nums">{detail}</div>
      )}
    </div>
  );
}
