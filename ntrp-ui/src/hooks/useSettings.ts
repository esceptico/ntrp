import { useState, useCallback, useEffect, useRef } from "react";
import { accentColors, themeNames, type AccentColor, type Theme } from "../components/ui/colors.js";
import { updateConfig } from "../api/client.js";
import type { Config } from "../types.js";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

export interface UiSettings {
  renderMarkdown: boolean;
  accentColor: AccentColor;
  theme: Theme;
}

export interface AgentSettings {
  maxDepth: number;
}

export interface Settings {
  ui: UiSettings;
  agent: AgentSettings;
}

const defaultSettings: Settings = {
  ui: {
    renderMarkdown: true,
    accentColor: "gray",
    theme: "dark",
  },
  agent: {
    maxDepth: 8,
  },
};

const SETTINGS_DIR = path.join(os.homedir(), ".ntrp");
const SETTINGS_FILE = path.join(SETTINGS_DIR, "settings.json");

function loadSettings(): Settings {
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      const data = fs.readFileSync(SETTINGS_FILE, "utf-8");
      const parsed = JSON.parse(data);
      if (typeof parsed !== "object" || parsed === null) return defaultSettings;
      const ui = { ...defaultSettings.ui, ...parsed.ui };
      if (!(ui.accentColor in accentColors)) ui.accentColor = defaultSettings.ui.accentColor;
      if (!themeNames.includes(ui.theme)) ui.theme = defaultSettings.ui.theme;
      return {
        ui,
        agent: { ...defaultSettings.agent, ...parsed.agent },
      };
    }
  } catch {
    // Ignore errors, use defaults
  }
  return defaultSettings;
}

function saveSettings(settings: Settings): void {
  try {
    if (!fs.existsSync(SETTINGS_DIR)) {
      fs.mkdirSync(SETTINGS_DIR, { recursive: true });
    }
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2));
  } catch {
    // Ignore save errors
  }
}

export function useSettings(config: Config) {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [showSettings, setShowSettings] = useState(false);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) {
      saveSettings(settings);
    } else {
      initializedRef.current = true;
    }
  }, [settings]);

  useEffect(() => {
    updateConfig(config, {
      max_depth: settings.agent.maxDepth,
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const updateSetting = useCallback(
    (category: keyof Settings, key: string, value: unknown) => {
      setSettings((prev) => {
        const updated = {
          ...prev,
          [category]: { ...prev[category], [key]: value },
        };

        if (category === "agent") {
          const agentPatch: Record<string, unknown> = {};
          if (key === "maxDepth") agentPatch.max_depth = value;
          updateConfig(config, agentPatch as { max_depth?: number }).catch(() => {});
        }

        return updated;
      });
    },
    [config]
  );

  const closeSettings = useCallback(() => setShowSettings(false), []);
  const toggleSettings = useCallback(() => setShowSettings((v) => !v), []);

  return {
    settings,
    showSettings,
    updateSetting,
    closeSettings,
    toggleSettings,
  };
}
