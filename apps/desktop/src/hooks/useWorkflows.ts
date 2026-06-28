import { useMemo } from "react";
import { useStore } from "@/stores";
import { selectWorkflowsForSession, type Workflow } from "@/stores/workflow-domain";

/** Workflows belonging to a session, derived from the workflow domain.
 *  Selecting `rows` (a stable reference between unrelated updates) and
 *  filtering in `useMemo` avoids returning a fresh array on every render —
 *  which would defeat zustand's Object.is bail-out and loop. */
export function useWorkflows(sessionId: string | null): Workflow[] {
  const rows = useStore((s) => s.workflows.rows);
  return useMemo(
    () => (sessionId ? selectWorkflowsForSession({ rows }, sessionId) : []),
    [rows, sessionId],
  );
}
