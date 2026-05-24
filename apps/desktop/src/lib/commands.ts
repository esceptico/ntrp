import { useMemo } from "react";

import { BUILTIN_COMMANDS } from "../actions/builtins";
import { useStore } from "../store";

export interface CommandEntry {
  name: string;
  description: string;
  kind: "builtin" | "skill";
}

export function useCommandList(): CommandEntry[] {
  const skills = useStore((s) => s.skills);
  return useMemo(() => {
    const builtins: CommandEntry[] = BUILTIN_COMMANDS
      .filter((c) => !c.hidden)
      .map((c) => ({
        name: c.name,
        description: c.description,
        kind: "builtin" as const,
      }));
    const skillEntries: CommandEntry[] = skills.map((s) => ({
      name: s.name,
      description: s.description || "Skill",
      kind: "skill" as const,
    }));
    return [...builtins, ...skillEntries];
  }, [skills]);
}

export function filterCommands(all: CommandEntry[], query: string): CommandEntry[] {
  const q = query.toLowerCase();
  if (!q) return all;
  return all.filter((c) => c.name.toLowerCase().startsWith(q));
}
