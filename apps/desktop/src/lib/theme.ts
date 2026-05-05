import { useEffect } from "react";
import { useStore, type ThemeChoice } from "../store";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function resolveDark(choice: ThemeChoice): boolean {
  if (choice === "dark") return true;
  if (choice === "light") return false;
  return window.matchMedia(DARK_QUERY).matches;
}

function apply(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (resolveDark(choice)) root.classList.add("dark");
  else root.classList.remove("dark");
}

/** Effect that keeps the <html> `dark` class in sync with the user's theme
 *  pref. When choice is "system", also subscribes to OS-level changes so
 *  the app flips automatically without needing a reload. */
export function useThemeEffect(): void {
  const choice = useStore((s) => s.prefs.theme);

  useEffect(() => {
    apply(choice);
    if (choice !== "system") return;
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = () => apply("system");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [choice]);
}
