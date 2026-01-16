/**
 * Shared terminal size hook with single global resize listener.
 * Based on patterns from Letta CLI and Gemini CLI.
 */
import { useState, useEffect } from "react";

interface TerminalSize {
  width: number;
  height: number;
}

type SizeListener = (size: TerminalSize) => void;

const listeners = new Set<SizeListener>();
let registered = false;

function getTerminalSize(): TerminalSize {
  return {
    width: process.stdout.columns || 80,
    height: process.stdout.rows || 24,
  };
}

function ensureResizeHandler() {
  if (registered) return;
  const stdout = process.stdout;
  if (stdout && stdout.on) {
    stdout.on("resize", () => {
      const size = getTerminalSize();
      listeners.forEach(fn => fn(size));
    });
    registered = true;
  }
}

export function useTerminalSize(): TerminalSize {
  const [size, setSize] = useState(getTerminalSize);

  useEffect(() => {
    ensureResizeHandler();
    const listener: SizeListener = setSize;
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return size;
}

export function useTerminalWidth(): number {
  return useTerminalSize().width;
}

export function useTerminalHeight(): number {
  return useTerminalSize().height;
}
