import React, { createContext, useContext, useEffect, useMemo } from "react";
import { accentColors, syncAccentColor, type AccentColor } from "../components/ui/colors.js";

interface AccentColorContextValue {
  accent: AccentColor;
  accentValue: string;
  shimmerValue: string;
}

const AccentColorContext = createContext<AccentColorContextValue>({
  accent: "blue",
  accentValue: accentColors.blue.primary,
  shimmerValue: accentColors.blue.shimmer,
});

interface AccentColorProviderProps {
  accent: AccentColor;
  children: React.ReactNode;
}

export function AccentColorProvider({ accent, children }: AccentColorProviderProps) {
  useEffect(() => {
    syncAccentColor(accent);
  }, [accent]);

  const value = useMemo(() => ({
    accent,
    accentValue: accentColors[accent].primary,
    shimmerValue: accentColors[accent].shimmer,
  }), [accent]);

  return (
    <AccentColorContext.Provider value={value}>
      {children}
    </AccentColorContext.Provider>
  );
}

export function useAccentColor() {
  return useContext(AccentColorContext);
}
