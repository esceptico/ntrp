import type { RuntimeRunStatus } from "../api";

export function isForegroundRunStatus(status: RuntimeRunStatus | string | null | undefined): boolean {
  return status === "pending" || status === "running";
}

export function isLiveRunStatus(status: RuntimeRunStatus | string | null | undefined): boolean {
  return isForegroundRunStatus(status) || status === "backgrounded";
}
