import type { AppConfig } from "../api";
import { apiWithConfig } from "../api";
import { queryString } from "./memoryItems";
import type { MemoryKind } from "./memoryItems";

export type MemoryArtifactKind = MemoryKind | "changelog" | "topic";

export interface MemoryArtifact {
  path: string;
  title: string;
  kind: MemoryArtifactKind;
  type: "file";
  directory: string;
  scope: { kind: string; key: string | null };
  content: string;
  snippet: string | null;
  record_count: number | null;
  generated: boolean;
  editable: boolean;
  readonly_reason: string | null;
  updated_at: string | null;
  labels: string[];
  source: string | null;
  timeline: Array<{
    id: string;
    text: string;
    kind: string;
    date: string;
    src: string;
    pinned: boolean;
    superseded: boolean;
  }>;
  frontmatter?: Record<string, string | number | boolean | null | Array<string | number | boolean | null>>;
}

export interface MemoryArtifactsResponse {
  artifacts: MemoryArtifact[];
}

export interface MemoryArtifactResponse {
  artifact: MemoryArtifact;
}

export function listMemoryArtifacts(config: AppConfig, params: { kind?: MemoryArtifactKind; q?: string } = {}) {
  return apiWithConfig<MemoryArtifactsResponse>(
    config,
    `/admin/memory/artifacts${queryString({ kind: params.kind, q: params.q })}`,
  );
}

function encodeArtifactPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function readMemoryArtifact(config: AppConfig, path: string) {
  return apiWithConfig<MemoryArtifactResponse>(config, `/admin/memory/artifacts/${encodeArtifactPath(path)}`);
}

export function rebuildMemoryArtifacts(config: AppConfig) {
  return apiWithConfig<MemoryArtifactsResponse>(config, "/admin/memory/artifacts/rebuild", { method: "POST" });
}
