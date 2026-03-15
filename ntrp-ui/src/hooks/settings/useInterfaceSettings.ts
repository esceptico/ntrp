import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import { SIDEBAR_SECTION_IDS } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

// Items: streaming, then sidebar toggles
const TOTAL_ITEMS = 1 + SIDEBAR_SECTION_IDS.length;

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
      if (interfaceIndex === 0) {
        onUpdate("ui", "streaming", !settings.ui.streaming);
      } else {
        const id = SIDEBAR_SECTION_IDS[interfaceIndex - 1];
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
