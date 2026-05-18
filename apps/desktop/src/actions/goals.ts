import { apiWithConfig, type SessionGoal } from "../api";
import { getState } from "../store";
import { appendError, appendStatus } from "./_shared";
import { enqueueMessage, sendMessage } from "./messages";

export async function fetchGoal(sessionId: string): Promise<void> {
  const s = getState();
  const goal = await apiWithConfig<SessionGoal | null>(s.config, `/sessions/${sessionId}/goal`);
  s.setGoal(sessionId, goal);
}

export async function setGoal(objective: string): Promise<SessionGoal | null> {
  const s = getState();
  if (!s.currentSessionId) return null;
  const trimmed = objective.trim();
  if (!trimmed) {
    const goal = s.goals[s.currentSessionId];
    appendStatus(goal ? `Goal: ${goal.objective} (${goal.status})` : "No active goal.");
    return goal ?? null;
  }
  try {
    const goal = await apiWithConfig<SessionGoal>(s.config, `/sessions/${s.currentSessionId}/goal`, {
      method: "POST",
      body: JSON.stringify({ objective: trimmed }),
    });
    s.setGoal(s.currentSessionId, goal);
    return goal;
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
    return null;
  }
}

export async function proposeGoal(): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  try {
    const proposal = await apiWithConfig<{ objective: string }>(
      s.config,
      `/sessions/${s.currentSessionId}/goal/propose`,
      { method: "POST" },
    );
    const objective = proposal.objective.trim();
    if (!objective) {
      appendError("Goal proposal was empty.");
      return;
    }
    s.setPendingGoalProposal({ sessionId: s.currentSessionId, objective });
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
  }
}

export async function acceptGoalProposal(): Promise<void> {
  const s = getState();
  const proposal = s.pendingGoalProposal;
  if (!proposal) return;
  try {
    const goal = await apiWithConfig<SessionGoal>(s.config, `/sessions/${proposal.sessionId}/goal`, {
      method: "POST",
      body: JSON.stringify({ objective: proposal.objective }),
    });
    s.setGoal(proposal.sessionId, goal);
    s.setPendingGoalProposal(null);
    const next = getState();
    if (next.currentSessionId === proposal.sessionId) {
      const prompt = `/goal ${goal.objective}`;
      if (next.running) {
        await enqueueMessage(prompt);
      } else {
        await sendMessage(prompt);
      }
    }
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
  }
}

export function editGoalProposal(): void {
  const s = getState();
  const proposal = s.pendingGoalProposal;
  if (!proposal) return;
  s.setDraft(`/goal ${proposal.objective}`);
  s.setPendingGoalProposal(null);
}

export function cancelGoalProposal(): void {
  getState().setPendingGoalProposal(null);
}

export async function updateGoal(status: SessionGoal["status"]): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  try {
    const goal = await apiWithConfig<SessionGoal>(s.config, `/sessions/${s.currentSessionId}/goal`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    s.setGoal(s.currentSessionId, goal);
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
  }
}

export async function clearGoal(): Promise<void> {
  const s = getState();
  if (!s.currentSessionId) return;
  try {
    await apiWithConfig(s.config, `/sessions/${s.currentSessionId}/goal`, { method: "DELETE" });
    s.setGoal(s.currentSessionId, null);
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
  }
}
