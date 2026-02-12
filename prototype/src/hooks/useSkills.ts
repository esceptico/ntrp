import { useState, useEffect, useCallback } from "react";
import type { Config } from "../types.js";
import { getSkills, installSkill, removeSkill, type Skill } from "../api/client.js";
import type { Key } from "./useKeypress.js";
import { useTextInput } from "./useTextInput.js";

export type SkillsMode = "list" | "install" | "confirm-delete";

export interface UseSkillsResult {
  mode: SkillsMode;
  skills: Skill[];
  selectedIndex: number;
  loading: boolean;
  installing: boolean;
  error: string | null;
  installSource: string;
  installCursor: number;
  handleKeypress: (key: Key) => void;
}

export function useSkills(config: Config): UseSkillsResult {
  const [mode, setMode] = useState<SkillsMode>("list");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [installSource, setInstallSource] = useState("");
  const [installCursor, setInstallCursor] = useState(0);

  const { handleKey: handleInstallKey } = useTextInput({
    text: installSource,
    cursorPos: installCursor,
    setText: setInstallSource,
    setCursorPos: setInstallCursor,
  });

  const fetchSkills = useCallback(async () => {
    try {
      const result = await getSkills(config);
      setSkills(result.skills);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleInstall = useCallback(async () => {
    if (installing || !installSource.trim()) return;
    setError(null);
    setInstalling(true);
    try {
      await installSkill(config, installSource.trim());
      await fetchSkills();
      setMode("list");
      setInstallSource("");
      setInstallCursor(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setInstalling(false);
    }
  }, [config, installSource, installing, fetchSkills]);

  const handleDelete = useCallback(async () => {
    const skill = skills[selectedIndex];
    if (!skill) return;
    try {
      await removeSkill(config, skill.name);
      await fetchSkills();
      setSelectedIndex((i) => Math.max(0, i - 1));
      setMode("list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    }
  }, [config, skills, selectedIndex, fetchSkills]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (mode === "list") {
        if (key.name === "up" || key.name === "k") {
          setSelectedIndex((i) => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setSelectedIndex((i) => Math.min(skills.length - 1, i + 1));
        } else if (key.sequence === "a") {
          setMode("install");
          setError(null);
        } else if ((key.sequence === "d" || key.name === "delete") && skills.length > 0) {
          setMode("confirm-delete");
        }
      } else if (mode === "install") {
        if (key.name === "escape") {
          setMode("list");
          setInstallSource("");
          setInstallCursor(0);
          setError(null);
        } else if (key.name === "return") {
          handleInstall();
        } else {
          handleInstallKey(key);
        }
      } else if (mode === "confirm-delete") {
        if (key.sequence === "y") {
          handleDelete();
        } else if (key.name === "escape" || key.sequence === "n") {
          setMode("list");
        }
      }
    },
    [mode, skills.length, handleInstall, handleDelete, handleInstallKey]
  );

  return {
    mode, skills, selectedIndex, loading, installing, error,
    installSource, installCursor, handleKeypress,
  };
}
