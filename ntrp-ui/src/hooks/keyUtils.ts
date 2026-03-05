import type { Key } from "./useKeypress.js";

export function handleListNav(
  key: Key,
  max: number,
  setIndex: (fn: (prev: number) => number) => void,
): boolean {
  if (key.name === "up" || key.name === "k") {
    setIndex(i => Math.max(0, i - 1));
    return true;
  }
  if (key.name === "down" || key.name === "j") {
    setIndex(i => Math.min(max - 1, i + 1));
    return true;
  }
  return false;
}
