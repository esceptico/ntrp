import type { Automation } from "@/api/types";
import { agentRunFromAutomation } from "@/lib/agentRun";
import { switchSession } from "@/actions/sessions";
import { useStore } from "@/stores";
import { AgentRunRow } from "@/components/ui/AgentRunRow";

// A running automation in the hub — the SAME agent body as a sub-agent run.
// An automation is the same abstraction as a parent/child agent, so it flows
// through the shared view-model and renders via AgentRunRow. The live stream
// status (if any) overrides the default progress line.
export function SidebarAutomationRow({
  automation,
  streamStatus,
}: {
  automation: Automation;
  streamStatus: string | undefined;
}) {
  const openAutomations = useStore((s) => s.openAutomations);
  const sessions = useStore((s) => s.sessions);
  const closeAutomations = useStore((s) => s.closeAutomations);
  const channel =
    sessions.find((sx) => sx.origin_automation_id === automation.task_id) ?? null;

  const base = agentRunFromAutomation(automation);
  const run = streamStatus ? { ...base, progress: streamStatus } : base;

  const open = channel
    ? () => {
        void switchSession(channel.session_id);
        closeAutomations();
      }
    : () => openAutomations();

  return <AgentRunRow run={run} onOpen={open} />;
}
