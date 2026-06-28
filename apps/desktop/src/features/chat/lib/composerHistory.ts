export interface HistoryState {
  /** null when not browsing history; otherwise the index into `sentMessages`. */
  historyIndex: number | null;
  /** Current composer text. Stashed on the first backward step so the newest
   *  ArrowDown can restore the in-progress draft. */
  draft: string;
  /** Snapshot of the draft taken when history browsing began. */
  stashedDraft: string;
}

export interface HistoryResult {
  value: string;
  historyIndex: number | null;
  stashedDraft: string;
}

/** Readline-style recall over previously-sent messages (oldest → newest).
 *  ArrowUp walks backward (most-recent first), stashing the live draft on the
 *  first step; ArrowDown walks forward, restoring the stash past the newest
 *  entry and exiting history mode. A no-op returns the inputs unchanged. */
export function recallHistory(
  state: HistoryState,
  direction: "up" | "down",
  sentMessages: string[],
): HistoryResult {
  const noop: HistoryResult = {
    value: state.draft,
    historyIndex: state.historyIndex,
    stashedDraft: state.stashedDraft,
  };

  if (sentMessages.length === 0) return noop;

  if (direction === "up") {
    const start = state.historyIndex == null ? sentMessages.length : state.historyIndex;
    if (start <= 0) return noop;
    const next = start - 1;
    return {
      value: sentMessages[next],
      historyIndex: next,
      stashedDraft: state.historyIndex == null ? state.draft : state.stashedDraft,
    };
  }

  if (state.historyIndex == null) return noop;
  const next = state.historyIndex + 1;
  if (next >= sentMessages.length) {
    return { value: state.stashedDraft, historyIndex: null, stashedDraft: state.stashedDraft };
  }
  return { value: sentMessages[next], historyIndex: next, stashedDraft: state.stashedDraft };
}
