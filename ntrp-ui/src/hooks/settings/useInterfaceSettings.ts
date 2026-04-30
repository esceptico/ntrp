import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import { SIDEBAR_SECTION_IDS } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

const UI_TOGGLE_KEYS = ["streaming", "showReasoning"] as const;
const TOTAL_ITEMS = UI_TOGGLE_KEYS.length + SIDEBAR_SECTION_IDS.length;

export interface UseInterfaceSettingsResult {
  interfaceIndex: number;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useInterfaceSettings(
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseInterfaceSettingsResult {
  const [interfaceIndex, setInterfaceIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    if (handleListNav(key, TOTAL_ITEMS, setInterfaceIndex)) {
      // handled
    } else if (key.name === "return" || key.name === "space") {
      if (interfaceIndex < UI_TOGGLE_KEYS.length) {
        const key = UI_TOGGLE_KEYS[interfaceIndex];
        onUpdate("ui", key, !settings.ui[key]);
      } else {
        const id = SIDEBAR_SECTION_IDS[interfaceIndex - UI_TOGGLE_KEYS.length];
        onUpdate("sidebar", id, !settings.sidebar[id]);
      }
    }
  }, [interfaceIndex, settings, onUpdate]);

  return {
    interfaceIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
