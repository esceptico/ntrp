import type { SliceDetail, SlicesOverview } from "@/api/slices";

export interface SlicesDomainState {
  overview: SlicesOverview | null;
  detailByKey: Record<string, SliceDetail>;
  openSliceKey: string | null;
  loading: boolean;
}

export function createSlicesDomainState(): SlicesDomainState {
  return {
    overview: null,
    detailByKey: {},
    openSliceKey: null,
    loading: false,
  };
}

export function reduceOverviewLoaded(
  state: SlicesDomainState,
  overview: SlicesOverview,
): SlicesDomainState {
  return {
    ...state,
    overview,
    loading: false,
  };
}

export function reduceDetailLoaded(state: SlicesDomainState, detail: SliceDetail): SlicesDomainState {
  return {
    ...state,
    detailByKey: { ...state.detailByKey, [detail.key]: detail },
    loading: false,
  };
}

export function reduceAskResolved(state: SlicesDomainState, key: string, askId: string): SlicesDomainState {
  const overview = state.overview
    ? {
        ...state.overview,
        focus: state.overview.focus.filter((a) => !(a.id === askId && a.slice_key === key)),
      }
    : null;

  const detail = state.detailByKey[key]
    ? {
        ...state.detailByKey[key],
        asks: state.detailByKey[key].asks.filter((a) => a.id !== askId),
      }
    : undefined;

  const detailByKey = detail ? { ...state.detailByKey, [key]: detail } : state.detailByKey;

  return {
    ...state,
    overview,
    detailByKey,
  };
}

export function reduceOpenSlice(state: SlicesDomainState, key: string | null): SlicesDomainState {
  return {
    ...state,
    openSliceKey: key,
  };
}

export function reduceAutonomyUpdated(
  state: SlicesDomainState,
  key: string,
  autonomy: "observe" | "act",
): SlicesDomainState {
  const detail = state.detailByKey[key];
  const detailByKey = detail
    ? { ...state.detailByKey, [key]: { ...detail, autonomy } }
    : state.detailByKey;

  const overview = state.overview
    ? {
        ...state.overview,
        slices: state.overview.slices.map((s) => (s.key === key ? { ...s, autonomy } : s)),
      }
    : null;

  return { ...state, detailByKey, overview };
}
