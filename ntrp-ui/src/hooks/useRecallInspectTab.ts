import { useCallback, useState } from "react";
import type { Config } from "../types.js";
import { inspectMemoryRecall, type MemoryRecallInspectResult } from "../api/client.js";
import { useTextInput } from "./useTextInput.js";
import type { Key } from "./useKeypress.js";

export interface RecallInspectTabState {
  query: string;
  cursorPos: number;
  result: MemoryRecallInspectResult | null;
  loading: boolean;
  error: string | null;
  scrollOffset: number;
  run: () => void;
  handleKeys: (key: Key) => void;
}

export function useRecallInspectTab(config: Config): RecallInspectTabState {
  const [query, setQuery] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const [result, setResult] = useState<MemoryRecallInspectResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scrollOffset, setScrollOffset] = useState(0);

  const textInput = useTextInput({ text: query, cursorPos, setText: setQuery, setCursorPos });

  const run = useCallback(() => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    inspectMemoryRecall(config, trimmed)
      .then((data) => {
        setResult(data);
        setScrollOffset(0);
      })
      .catch((e: unknown) => setError(`Recall inspect failed: ${e}`))
      .finally(() => setLoading(false));
  }, [config, query, loading]);

  const handleKeys = useCallback(
    (key: Key) => {
      if (key.name === "return") {
        run();
        return;
      }
      if (key.name === "up") {
        setScrollOffset((value) => Math.max(0, value - 1));
        return;
      }
      if (key.name === "down") {
        setScrollOffset((value) => value + 1);
        return;
      }
      if (key.ctrl && key.name === "u") {
        setQuery("");
        setCursorPos(0);
        setError(null);
        return;
      }
      textInput.handleKey(key);
    },
    [run, textInput],
  );

  return {
    query,
    cursorPos,
    result,
    loading,
    error,
    scrollOffset,
    run,
    handleKeys,
  };
}
