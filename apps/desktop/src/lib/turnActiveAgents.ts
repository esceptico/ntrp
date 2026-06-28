import { SEMANTIC_KIND_AGENT } from "@/lib/agent";
import type { BackgroundAgent, UiMessage } from "@/store";
import { isActiveBackgroundAgent } from "@/store/background-agent-domain";

interface TurnActiveChildAgentInput {
  childIds: readonly string[];
  messages: ReadonlyMap<string, UiMessage>;
  backgroundAgents: Record<string, BackgroundAgent>;
  sessionId: string | null;
}

export function turnHasActiveChildAgent({
  childIds,
  messages,
  backgroundAgents,
  sessionId,
}: TurnActiveChildAgentInput): boolean {
  if (!sessionId) return false;

  const refs = collectTurnChildAgentRefs(childIds, messages);
  if (!refs.parentToolCallIds.size && !refs.childRunIds.size && !refs.childSessionIds.size) {
    return false;
  }

  return Object.values(backgroundAgents).some((agent) => {
    if (agent.sessionId !== sessionId || !isActiveBackgroundAgent(agent)) return false;
    if (agent.parentToolCallId && refs.parentToolCallIds.has(agent.parentToolCallId)) return true;
    if (agent.childSessionId && refs.childSessionIds.has(agent.childSessionId)) return true;
    return refs.childRunIds.has(agent.taskId);
  });
}

function collectTurnChildAgentRefs(
  childIds: readonly string[],
  messages: ReadonlyMap<string, UiMessage>,
): {
  parentToolCallIds: Set<string>;
  childRunIds: Set<string>;
  childSessionIds: Set<string>;
} {
  const parentToolCallIds = new Set<string>();
  const childRunIds = new Set<string>();
  const childSessionIds = new Set<string>();

  for (const id of childIds) {
    const items = messages.get(id)?.activity?.items ?? [];
    for (const item of items) {
      if (item.semanticKind !== SEMANTIC_KIND_AGENT && !item.childAgent) continue;
      parentToolCallIds.add(item.id);
      if (item.childAgent?.parentToolCallId) {
        parentToolCallIds.add(item.childAgent.parentToolCallId);
      }
      if (item.childAgent?.childRunId) childRunIds.add(item.childAgent.childRunId);
      if (item.childAgent?.childSessionId) childSessionIds.add(item.childAgent.childSessionId);
      if (item.runId) childRunIds.add(item.runId);
    }
  }

  return { parentToolCallIds, childRunIds, childSessionIds };
}
