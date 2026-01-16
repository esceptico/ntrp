/**
 * Dimensions context for providing terminal dimensions to all components.
 * Based on patterns from Gemini CLI.
 */
import React, { createContext, useContext, useMemo } from "react";
import { useTerminalSize } from "../hooks/useTerminalSize.js";

interface Dimensions {
  width: number;
  height: number;
  contentWidth: number;  // width - 2 (for padding)
}

const DimensionsContext = createContext<Dimensions>({
  width: 80,
  height: 24,
  contentWidth: 78,
});

interface DimensionsProviderProps {
  children: React.ReactNode;
  padding?: number;
}

export function DimensionsProvider({ children, padding = 2 }: DimensionsProviderProps) {
  const { width, height } = useTerminalSize();

  const dimensions = useMemo<Dimensions>(() => ({
    width,
    height,
    contentWidth: Math.max(0, width - padding),
  }), [width, height, padding]);

  return (
    <DimensionsContext.Provider value={dimensions}>
      {children}
    </DimensionsContext.Provider>
  );
}

export function useDimensions(): Dimensions {
  return useContext(DimensionsContext);
}

export function useContentWidth(): number {
  return useDimensions().contentWidth;
}
