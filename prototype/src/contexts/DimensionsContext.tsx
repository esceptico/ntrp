import React, { createContext, useContext, useMemo } from "react";
import { useTerminalDimensions } from "@opentui/react";

interface Dimensions {
  width: number;
  height: number;
  contentWidth: number;
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
  const { width, height } = useTerminalDimensions();

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
