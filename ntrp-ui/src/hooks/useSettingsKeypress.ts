import { useCallback, useMemo } from "react";
import { useKeypress } from "./useKeypress.js";
import type { Key } from "./useKeypress.js";
import type { UseSettingsStateResult } from "./useSettingsState.js";
import type { SectionId } from "../components/dialogs/settings/config.js";
import { SECTION_IDS } from "../components/dialogs/settings/config.js";

export interface UseSettingsKeypressOptions {
  state: UseSettingsStateResult;
  activeSection: SectionId;
  drilled: boolean;
  setDrilled: React.Dispatch<React.SetStateAction<boolean>>;
  setActiveSection: React.Dispatch<React.SetStateAction<SectionId>>;
  onClose: () => void;
}

interface SectionHandler {
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useSettingsKeypress({
  state,
  activeSection,
  drilled,
  setDrilled,
  setActiveSection,
  onClose,
}: UseSettingsKeypressOptions): void {
  const sectionHandlers: Record<SectionId, SectionHandler> = useMemo(() => ({
    connection: state.server,
    apiKeys: state.apiKeys,
    integrations: state.connections,
    memory: state.memory,
    instructions: state.directives,
    context: state.context,
    agent: state.agent,
    notifications: state.notifiers,
    skills: state.skills,
    mcp: state.mcp,
    interface: state.iface,
  }), [state]);

  const handleKeypress = useCallback((key: Key) => {
    if (state.connections.actionInProgress || state.memory.actionInProgress) return;

    if (key.name === "escape" || key.name === "q") {
      if (drilled) {
        const handler = sectionHandlers[activeSection];
        if (handler.isEditing) {
          handler.cancelEdit();
        } else {
          setDrilled(false);
        }
        return;
      }
      onClose();
      return;
    }

    if (!drilled) {
      const idx = SECTION_IDS.indexOf(activeSection);
      if (key.name === "up" || key.name === "k") {
        if (idx > 0) setActiveSection(SECTION_IDS[idx - 1]);
      } else if (key.name === "down" || key.name === "j") {
        if (idx < SECTION_IDS.length - 1) setActiveSection(SECTION_IDS[idx + 1]);
      } else if (key.name === "return" || key.name === "space") {
        setDrilled(true);
      }
      return;
    }

    sectionHandlers[activeSection].handleKeypress(key);
  }, [
    drilled, activeSection, sectionHandlers,
    state.connections.actionInProgress, state.memory.actionInProgress,
    onClose, setDrilled, setActiveSection,
  ]);

  useKeypress(handleKeypress, {
    isActive: !state.connections.showingBrowserDropdown,
  });
}
