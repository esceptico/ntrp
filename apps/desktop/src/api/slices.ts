import { apiWithConfig, type AppConfig } from "@/api/core";

export interface SliceSummary {
  key: string;
  title: string;
  autonomy: "observe" | "act";
  live: boolean;
  updated: string;
  ask_count: number;
}

export interface SliceAsk {
  id: string;
  slice_key: string;
  text: string;
  kind: "review" | "decide" | "act" | "drift";
  source: string;
  actions: { verb: string; ref: string }[];
  state: string;
  created_at: string;
  snoozed_until: string | null;
  provenance?: string | null;
}

export interface SlicesOverview {
  slices: SliceSummary[];
  focus: SliceAsk[];
}

export interface SliceDetail {
  key: string;
  title: string;
  autonomy: "observe" | "act";
  page_path: string;
  related: string[];
  open_loops: string[];
  updated: string;
  asks: SliceAsk[];
  sessions: { session_id: string; name: string }[];
  automations: unknown[];
}

export async function fetchSlicesOverview(config: AppConfig): Promise<SlicesOverview> {
  return apiWithConfig<SlicesOverview>(config, "/slices");
}

export async function fetchSliceDetail(config: AppConfig, key: string): Promise<SliceDetail> {
  return apiWithConfig<SliceDetail>(config, `/slices/${encodeURIComponent(key)}`);
}

export async function resolveAsk(
  config: AppConfig,
  key: string,
  askId: string,
  state: string,
  snoozedUntil?: string,
): Promise<SliceAsk> {
  const body: { state: string; snoozed_until?: string } = { state };
  if (snoozedUntil) body.snoozed_until = snoozedUntil;
  return apiWithConfig<SliceAsk>(config, `/slices/${encodeURIComponent(key)}/asks/${encodeURIComponent(askId)}/resolve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Server returns the slice registry record (key/title/autonomy/page_path/
// related) — not a full SliceDetail (no asks/sessions/automations). The
// action layer merges just the autonomy field into any cached detail.
export interface SliceRegistryRecord {
  key: string;
  title: string;
  autonomy: "observe" | "act";
  page_path: string;
  related: string[];
}

export async function updateSliceAutonomy(
  config: AppConfig,
  key: string,
  autonomy: "observe" | "act",
): Promise<SliceRegistryRecord> {
  return apiWithConfig<SliceRegistryRecord>(config, `/slices/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify({ autonomy }),
  });
}
