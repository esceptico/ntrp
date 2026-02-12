export interface ToolChainItem {
  id: string;
  type: "task" | "tool";
  depth: number;
  name: string;
  description?: string;
  result?: string;
  preview?: string;
  data?: Record<string, unknown>;
  status: "pending" | "running" | "done" | "error";
  seq?: number;
  parentId?: string;
  startTime?: number;
  endTime?: number;
}
