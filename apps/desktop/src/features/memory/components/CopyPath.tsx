import { useState } from "react";
import { GhostBtn } from "@/features/memory/components/shared";

export function CopyPath({ path }: { path: string }) {
  const [state, setState] = useState<"idle" | "copied" | "unavailable">("idle");

  const copy = async () => {
    let ok = false;
    try {
      // Electron's native clipboard (main process) — unlike navigator.clipboard
      // it doesn't fail when the document isn't focused.
      ok = (await window.ntrpDesktop?.clipboard?.writeText(path)) ?? false;
      if (!ok && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(path);
        ok = true;
      }
    } catch {
      ok = false;
    }
    setState(ok ? "copied" : "unavailable");
    window.setTimeout(() => setState("idle"), 1200);
  };

  return (
    <GhostBtn onClick={() => void copy()}>
      {state === "copied" ? "Copied" : state === "unavailable" ? "Copy unavailable" : "Copy path"}
    </GhostBtn>
  );
}
