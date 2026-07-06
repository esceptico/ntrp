import { switchSession } from "@/actions/sessions";

interface SliceSessionRow {
  session_id: string;
  name: string;
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
    <div className="grid gap-2">
      <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Activity</span>
      <div className="grid gap-px">
        {sessions.map((session) => (
          <button
            key={session.session_id}
            type="button"
            onClick={() => void switchSession(session.session_id)}
            className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-left text-sm text-ink-soft hover:bg-surface-soft"
          >
            <span className="min-w-0 flex-1 truncate">{session.name || "Untitled session"}</span>
          </button>
        ))}
        {automationRows.map((auto, index) => (
          <div
            key={`${auto.name}-${index}`}
            className="flex items-center gap-2 px-3 py-2 text-sm text-ink-soft"
          >
            <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-faint" />
            <span className="min-w-0 flex-1 truncate">{auto.name}</span>
            {auto.running_since && <span className="shrink-0 text-2xs text-faint">running</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
