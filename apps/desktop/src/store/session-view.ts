import type { HistoryPage } from "../api";
import type { HistoryPhase } from "./domains";

export interface SessionViewState {
  currentSessionId: string | null;
  historyPhase: HistoryPhase;
  cachePreviewRestoredFor: string | null;
  canonicalHistoryRequired: boolean;
  historyLoadedFor: string | null;
  historyReloadingFor: string | null;
  historyHasMoreBefore: boolean;
  historyHasMoreAfter: boolean;
  historyLoadingBefore: boolean;
  historyLoadingAfter: boolean;
}

export type HistoryPageMergeMode = "replace" | "prepend" | "append";

export function createInitialSessionViewState(): SessionViewState {
  return {
    currentSessionId: null,
    historyPhase: "idle",
    cachePreviewRestoredFor: null,
    canonicalHistoryRequired: false,
    historyLoadedFor: null,
    historyReloadingFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceSessionSelected(
  state: SessionViewState,
  sessionId: string | null,
): SessionViewState {
  if (sessionId === null) return createInitialSessionViewState();
  if (state.currentSessionId === sessionId) return state;

  return {
    ...createInitialSessionViewState(),
    currentSessionId: sessionId,
    canonicalHistoryRequired: true,
  };
}

export function reduceCachePreviewRestored(
  state: SessionViewState,
  sessionId: string,
): SessionViewState {
  return {
    ...state,
    currentSessionId: sessionId,
    historyPhase: "cached-preview",
    cachePreviewRestoredFor: sessionId,
    canonicalHistoryRequired: true,
    historyLoadedFor: null,
    historyReloadingFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceHistoryLoadStarted(
  state: SessionViewState,
  sessionId: string,
): SessionViewState {
  return {
    ...state,
    currentSessionId: sessionId,
    historyPhase: "loading-history",
    canonicalHistoryRequired: true,
    historyReloadingFor: sessionId,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceHistoryLoadSucceeded(
  state: SessionViewState,
  sessionId: string,
  page?: HistoryPage,
  mode: HistoryPageMergeMode = "replace",
): SessionViewState {
  return {
    ...state,
    currentSessionId: sessionId,
    historyPhase: "idle",
    cachePreviewRestoredFor: null,
    canonicalHistoryRequired: false,
    historyLoadedFor: sessionId,
    historyReloadingFor: null,
    historyHasMoreBefore: historyHasMoreBeforeAfterSuccess(state, page, mode),
    historyHasMoreAfter: historyHasMoreAfterAfterSuccess(state, page, mode),
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceHistoryLoadFailed(
  state: SessionViewState,
  sessionId: string,
): SessionViewState {
  if (state.currentSessionId !== sessionId && state.historyReloadingFor !== sessionId) {
    return state;
  }

  return {
    ...state,
    historyPhase:
      state.cachePreviewRestoredFor === sessionId ? "cached-preview" : "idle",
    canonicalHistoryRequired: true,
    historyReloadingFor: null,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceReplayGapDetected(
  state: SessionViewState,
  sessionId: string,
): SessionViewState {
  return {
    ...state,
    currentSessionId: sessionId,
    historyPhase: "replay-gap",
    cachePreviewRestoredFor: null,
    canonicalHistoryRequired: true,
    historyLoadedFor: null,
    historyReloadingFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
  };
}

export function reduceHistoryPageLoading(
  state: SessionViewState,
  direction: "before" | "after",
  loading: boolean,
): SessionViewState {
  return direction === "before"
    ? { ...state, historyLoadingBefore: loading }
    : { ...state, historyLoadingAfter: loading };
}

export function legacyFieldsFromSessionView(state: SessionViewState) {
  return {
    currentSessionId: state.currentSessionId,
    historyLoadedFor: state.historyLoadedFor,
    historyReloadingFor: state.historyReloadingFor,
    historyHasMoreBefore: state.historyHasMoreBefore,
    historyHasMoreAfter: state.historyHasMoreAfter,
    historyLoadingBefore: state.historyLoadingBefore,
    historyLoadingAfter: state.historyLoadingAfter,
  };
}

function historyHasMoreBeforeAfterSuccess(
  state: SessionViewState,
  page: HistoryPage | undefined,
  mode: HistoryPageMergeMode,
): boolean {
  if (mode === "append") return state.historyHasMoreBefore || Boolean(page?.has_more_before);
  return page?.has_more_before ?? false;
}

function historyHasMoreAfterAfterSuccess(
  state: SessionViewState,
  page: HistoryPage | undefined,
  mode: HistoryPageMergeMode,
): boolean {
  if (mode === "prepend") return state.historyHasMoreAfter || Boolean(page?.has_more_after);
  return page?.has_more_after ?? false;
}
