import React, { createContext, useContext, useEffect, useMemo } from "react";
import { accentColors, syncAccentColor, type AccentColor, type Theme } from "../components/ui/colors.js";

interface AccentColorContextValue {
  accent: AccentColor;
  accentValue: string;
  shimmerValue: string;
}

const AccentColorContext = createContext<AccentColorContextValue>({
  accent: "gray",
  accentValue: accentColors.gray.primary,
  shimmerValue: accentColors.gray.shimmer,
});

interface AccentColorProviderProps {
  accent: AccentColor;
  theme: Theme;
  children: React.ReactNode;
}

export function AccentColorProvider({ accent, theme, children }: AccentColorProviderProps) {
  useEffect(() => {
    syncAccentColor(accent);
  }, [accent]);

  // accentColors is mutated in place by setTheme() before this renders,
  // so reading it here gives the current theme's values.
  // theme dep forces recompute when theme changes.
  const value = useMemo(() => ({
    accent,
    accentValue: accentColors[accent].primary,
    shimmerValue: accentColors[accent].shimmer,
  }), [accent, theme]);

  return (
    <AccentColorContext.Provider value={value}>
      {children}
    </AccentColorContext.Provider>
  );
}

export function useAccentColor() {
  return useContext(AccentColorContext);
}
