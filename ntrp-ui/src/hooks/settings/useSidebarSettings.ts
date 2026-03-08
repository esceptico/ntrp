import { useCallback, useState } from "react";
import type { Settings } from "../useSettings.js";
import { SIDEBAR_SECTION_IDS } from "../useSettings.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export interface UseSidebarSettingsResult {
  sidebarIndex: number;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useSidebarSettings(
  settings: Settings,
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void,
): UseSidebarSettingsResult {
  const [sidebarIndex, setSidebarIndex] = useState(0);

  const handleKeypress = useCallback((key: Key) => {
    if (handleListNav(key, SIDEBAR_SECTION_IDS.length, setSidebarIndex)) {
      // handled
    } else if (key.name === "return" || key.name === "space") {
      const id = SIDEBAR_SECTION_IDS[sidebarIndex];
      onUpdate("sidebar", id, !settings.sidebar[id]);
    }
  }, [sidebarIndex, settings, onUpdate]);

  return {
    sidebarIndex,
    handleKeypress,
    isEditing: false,
    cancelEdit: () => {},
  };
}
