import type { DashboardOverview } from "../../../api/client.js";
import { colors } from "../../ui/colors.js";

interface BackgroundPanelProps {
  data: DashboardOverview;
  width: number;
}

const B = colors.text.disabled;

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

type Status = "ok" | "active" | "error" | "idle";

function pillColor(s: Status): string {
  switch (s) {
    case "ok": return colors.status.success;
    case "active": return colors.status.warning;
    case "error": return colors.status.error;
    case "idle": return B;
  }
}

export function BackgroundPanel({ data, width }: BackgroundPanelProps) {
  const { background, memory } = data;
  const { indexer, scheduler, consolidation } = background;

  const idxStatus: Status = indexer.status === "done" ? "ok"
    : indexer.status === "indexing" ? "active"
    : indexer.status === "error" ? "error"
    : "idle";

  return (
    <box flexDirection="column" marginTop={1}>
      <box>
        <text><span fg={B}>{"indexer".padEnd(18)}</span></text>
        <text><span fg={pillColor(idxStatus)}>[{idxStatus}]</span></text>
        {indexer.status === "indexing" && (
          <text><span fg={B}>{" "}{indexer.progress_done}/{indexer.progress_total}</span></text>
        )}
        {indexer.error && <text><span fg={colors.status.error}>{" "}{indexer.error}</span></text>}
      </box>
      <box>
        <text><span fg={B}>{"scheduler".padEnd(18)}</span></text>
        <text>
          <span fg={pillColor(scheduler.running ? "active" : "idle")}>
            [{scheduler.running ? "active" : "idle"}]
          </span>
        </text>
        {scheduler.enabled_count > 0 && (
          <text><span fg={B}>{" "}{scheduler.enabled_count} tasks</span></text>
        )}
        {scheduler.next_run_at && (
          <text><span fg={B}>{" · next "}{formatTime(scheduler.next_run_at)}</span></text>
        )}
      </box>
      {scheduler.active_task && (
        <box marginLeft={18}>
          <text><span fg={colors.status.warning}>{"→ "}{scheduler.active_task}</span></text>
        </box>
      )}
      <box>
        <text><span fg={B}>{"consolidation".padEnd(18)}</span></text>
        <text>
          <span fg={pillColor(consolidation.running ? "active" : "idle")}>
            [{consolidation.running ? "active" : "idle"}]
          </span>
        </text>
        {memory.unconsolidated > 0 && (
          <text><span fg={B}>{" "}{memory.unconsolidated} pending</span></text>
        )}
        {memory.last_consolidation_at && (
          <text><span fg={B}>{" · "}{relativeTime(memory.last_consolidation_at)}</span></text>
        )}
      </box>

      <box marginTop={1}>
        <text><span fg={B}>{"memory  "}</span></text>
        <text><span fg={colors.text.primary}><strong>{memory.fact_count}</strong></span></text>
        <text><span fg={B}>{" facts   "}</span></text>
        <text><span fg={colors.text.primary}><strong>{memory.observation_count}</strong></span></text>
        <text><span fg={B}>{" obs"}</span></text>
      </box>

      {memory.recent_facts.length > 0 && (
        <box flexDirection="column" marginTop={1}>
          {memory.recent_facts.map((fact) => (
            <box key={fact.id}>
              <text><span fg={B}>{relativeTime(fact.ts).padEnd(10)}</span></text>
              <text><span fg={colors.text.muted}>{fact.text}</span></text>
            </box>
          ))}
        </box>
      )}
    </box>
  );
}
