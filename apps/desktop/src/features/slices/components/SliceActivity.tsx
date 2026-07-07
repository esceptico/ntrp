import { switchSession } from "@/actions/sessions";
import { formatRelativePast } from "@/lib/format";

interface SliceSessionRow {
  session_id: string;
  name: string;
  last_activity?: string;
}

// Server-side `_slice_automations` shape (ntrp/slices/service.py) — name +
// run bookkeeping. `SliceDetail.automations` is typed `unknown[]` on the
// wire since the slice service passes raw dicts through; narrow here at
// the render boundary rather than widening the shared API type.
interface SliceAutomationRow {
  name?: string;
  running_since?: string | null;
  last_run_at?: string | null;
}

function isAutomationRow(value: unknown): value is SliceAutomationRow {
  return typeof value === "object" && value !== null && "name" in value;
}

/** ACTIVITY: quiet rows for the slice's sessions and automation runs.
 *  Sessions are click-through (switchSession); automations are read-only
 *  status rows here — the primary retry action for a failing automation
 *  lives on its ask card, not this list. */
export function SliceActivity({
  sessions,
  automations,
}: {
  sessions: SliceSessionRow[];
  automations: unknown[];
}) {
  const automationRows = automations.filter(isAutomationRow);
  if (sessions.length === 0 && automationRows.length === 0) return null;

  return (
    <div className="grid min-w-0 gap-2">
      <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Activity</span>
      {/* min-w-0 down the chain: rows truncate, so their min-content is the
          full untruncated line — without it long names blow the grid track
          past the column (same trap as OpenLoops/modal headers). */}
      <div className="grid min-w-0 gap-px">
        {sessions.map((session) => (
          <button
            key={session.session_id}
            type="button"
            onClick={() => void switchSession(session.session_id)}
            className="flex min-w-0 items-center gap-2 rounded-[8px] px-3 py-2 text-left text-sm text-ink-soft hover:bg-surface-soft"
          >
            <span className="min-w-0 flex-1 truncate">{session.name || "Untitled session"}</span>
            {session.last_activity && (
              <span className="shrink-0 text-2xs text-whisper tabular-nums">
                {formatRelativePast(session.last_activity)} ago
              </span>
            )}
          </button>
        ))}
        {automationRows.map((auto, index) => (
          <div
            key={`${auto.name}-${index}`}
            className="flex min-w-0 items-center gap-2 px-3 py-2 text-sm text-ink-soft"
          >
            <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-faint" />
            <span className="min-w-0 flex-1 truncate">{auto.name}</span>
            {auto.running_since ? (
              <span className="shrink-0 text-2xs text-faint">running</span>
            ) : (
              auto.last_run_at && (
                <span className="shrink-0 text-2xs text-whisper tabular-nums">
                  {formatRelativePast(auto.last_run_at)} ago
                </span>
              )
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
