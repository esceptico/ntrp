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
  provenance?: string | null;
}

export interface SlicesOverview {
  slices: SliceSummary[];
  focus: SliceAsk[];
}

export interface SliceDetail extends SliceSummary {
  open_loops: string[];
  asks: SliceAsk[];
  sessions: { session_id: string; name: string }[];
  automations: unknown[];
  page_path: string;
  related: string[];
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
