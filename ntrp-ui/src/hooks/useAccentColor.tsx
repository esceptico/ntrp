import React, { createContext, useContext, useMemo } from "react";
import { currentAccent, useThemeVersion } from "../components/ui/colors.js";

interface AccentColorContextValue {
  accentValue: string;
  shimmerValue: string;
}

const AccentColorContext = createContext<AccentColorContextValue>({
  accentValue: currentAccent.primary,
  shimmerValue: currentAccent.shimmer,
});

export function AccentColorProvider({ children }: { children: React.ReactNode }) {
  const themeVersion = useThemeVersion();

  const value = useMemo(() => ({
    accentValue: currentAccent.primary,
    shimmerValue: currentAccent.shimmer,
  }), [themeVersion]);

  return (
    <AccentColorContext.Provider value={value}>
      {children}
    </AccentColorContext.Provider>
  );
}

export function useAccentColor() {
  return useContext(AccentColorContext);
}
