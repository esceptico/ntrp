import { fetchSlicesOverview as fetchSlicesOverviewApi, fetchSliceDetail as fetchSliceDetailApi, resolveAsk as resolveAskApi } from "@/api/slices";
import { getState } from "@/stores";

export async function fetchSlicesOverview(): Promise<void> {
  const s = getState();
  try {
    const overview = await fetchSlicesOverviewApi(s.config);
    s.slicesOverviewLoaded(overview);
  } catch {
    /* leave previous overview in place */
  }
}

export async function fetchSliceDetail(key: string): Promise<void> {
  const s = getState();
  const detail = await fetchSliceDetailApi(s.config, key);
  s.sliceDetailLoaded(detail);
}

export async function resolveAsk(key: string, askId: string, state: string, snoozedUntil?: string): Promise<void> {
  const s = getState();
  await resolveAskApi(s.config, key, askId, state, snoozedUntil);
  s.sliceAskResolved(key, askId);
}
