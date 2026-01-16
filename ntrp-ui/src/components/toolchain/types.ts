export interface ToolChainItem {
  id: string;
  type: "task" | "tool";
  depth: number;
  name: string;
  description?: string;
  result?: string;
  preview?: string;
  metadata?: { diff?: string; lines_changed?: number };
  status: "pending" | "running" | "done" | "error";
  seq?: number;
  parentId?: string;
  startTime?: number;
  endTime?: number;
}
