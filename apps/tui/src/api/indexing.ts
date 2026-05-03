import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface IndexStatus {
  indexing: boolean;
  progress: {
    total: number;
    done: number;
    status: string;
    updated?: number;
    deleted?: number;
  };
  reembedding?: boolean;
  reembed_progress?: { total: number; done: number } | null;
  error?: string;
  stats: Record<string, number>;
}

export async function getIndexStatus(config: Config): Promise<IndexStatus> {
  return api.get<IndexStatus>(`${config.serverUrl}/index/status`);
}

export async function startIndexing(config: Config): Promise<{ status: string }> {
  return api.post<{ status: string }>(`${config.serverUrl}/index/start`);
}
