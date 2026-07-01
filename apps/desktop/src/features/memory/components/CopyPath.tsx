import { useState } from "react";
import { GhostBtn } from "@/features/memory/components/shared";
import { copyText } from "@/lib/clipboard";

export function CopyPath({ path }: { path: string }) {
  const [state, setState] = useState<"idle" | "copied" | "unavailable">("idle");

  const copy = async () => {
    const ok = await copyText(path);
    setState(ok ? "copied" : "unavailable");
    window.setTimeout(() => setState("idle"), 1200);
  };

  return (
    <GhostBtn onClick={() => void copy()}>
      {state === "copied" ? "Copied" : state === "unavailable" ? "Copy unavailable" : "Copy path"}
    </GhostBtn>
  );
}
