import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import { getDirectives, updateDirectives } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";

export interface UseDirectivesResult {
  directivesContent: string;
  directivesCursorPos: number;
  editingDirectives: boolean;
  savingDirectives: boolean;
  directivesError: string | null;
  handleSaveDirectives: () => Promise<void>;
  handleCancelDirectives: () => void;
  handleStartDirectivesEdit: () => void;
  handleDirectivesKey: (key: Key) => boolean;
  loadDirectives: () => void;
}

export function useDirectives(config: Config): UseDirectivesResult {
  const [directivesContent, setDirectivesContent] = useState("");
  const [directivesSaved, setDirectivesSaved] = useState("");
  const [directivesCursorPos, setDirectivesCursorPos] = useState(0);
  const [editingDirectives, setEditingDirectives] = useState(false);
  const [savingDirectives, setSavingDirectives] = useState(false);
  const [directivesError, setDirectivesError] = useState<string | null>(null);

  const { handleKey: handleDirectivesKey } = useTextInput({
    text: directivesContent,
    cursorPos: directivesCursorPos,
    setText: setDirectivesContent,
    setCursorPos: setDirectivesCursorPos,
  });

  const loadDirectives = useCallback(() => {
    getDirectives(config)
      .then((result) => {
        setDirectivesContent(result.content);
        setDirectivesSaved(result.content);
      })
      .catch(() => {});
  }, [config]);

  const handleSaveDirectives = useCallback(async () => {
    if (savingDirectives) return;
    setSavingDirectives(true);
    setDirectivesError(null);
    try {
      const result = await updateDirectives(config, directivesContent);
      setDirectivesSaved(result.content);
      setDirectivesContent(result.content);
      setEditingDirectives(false);
    } catch (e) {
      setDirectivesError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSavingDirectives(false);
    }
  }, [config, directivesContent, savingDirectives]);

  const handleCancelDirectives = useCallback(() => {
    setDirectivesContent(directivesSaved);
    setDirectivesCursorPos(0);
    setEditingDirectives(false);
  }, [directivesSaved]);

  const handleStartDirectivesEdit = useCallback(() => {
    setDirectivesCursorPos(directivesContent.length);
    setEditingDirectives(true);
  }, [directivesContent]);

  return {
    directivesContent,
    directivesCursorPos,
    editingDirectives,
    savingDirectives,
    directivesError,
    handleSaveDirectives,
    handleCancelDirectives,
    handleStartDirectivesEdit,
    handleDirectivesKey,
    loadDirectives,
  };
}
