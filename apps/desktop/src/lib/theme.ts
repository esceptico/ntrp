import { useEffect } from "react";
import { useStore, type ThemeChoice } from "@/stores";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function resolveDark(choice: ThemeChoice): boolean {
  if (choice === "dark") return true;
  if (choice === "light") return false;
  return window.matchMedia(DARK_QUERY).matches;
}

function applyDarkMode(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (resolveDark(choice)) root.classList.add("dark");
  else root.classList.remove("dark");
}

/** Effect that keeps the <html> `dark` class in sync with the user's
 *  prefs. When theme is "system", also subscribes to OS-level changes
 *  so the app flips automatically without a reload. */
export function useThemeEffect(): void {
  const theme = useStore((s) => s.prefs.theme);

  useEffect(() => {
    applyDarkMode(theme);
    if (theme !== "system") return;
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = () => applyDarkMode("system");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme]);
}
