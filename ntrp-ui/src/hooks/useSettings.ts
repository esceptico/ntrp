import { useState, useCallback, useEffect, useRef } from "react";
import { accentNames, themeNames, type AccentColor, type Theme } from "../components/ui/colors.js";
import { updateConfig } from "../api/client.js";
import type { Config } from "../types.js";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

export interface UiSettings {
  accentColor: AccentColor;
  theme: Theme;
  transparentBg: boolean;
  streaming: boolean;
}

export interface AgentSettings {
  maxDepth: number;
  compressionThreshold: number;
  maxMessages: number;
  compressionKeepRatio: number;
  summaryMaxTokens: number;
  consolidationInterval: number;
}

export const SIDEBAR_SECTION_IDS = ["models", "context", "usage", "sources", "automations", "sessions", "memory_stats"] as const;
export type SidebarSectionId = (typeof SIDEBAR_SECTION_IDS)[number];

export type SidebarSettings = Record<SidebarSectionId, boolean>;

export interface Settings {
  ui: UiSettings;
  agent: AgentSettings;
  sidebar: SidebarSettings;
}

const defaultSettings: Settings = {
  ui: {
    accentColor: "blue",
    theme: "dark",
    transparentBg: false,
    streaming: true,
  },
  agent: {
    maxDepth: 8,
    compressionThreshold: 80,
    maxMessages: 120,
    compressionKeepRatio: 20,
    summaryMaxTokens: 1500,
    consolidationInterval: 30,
  },
  sidebar: {
    models: true,
    context: true,
    usage: true,
    sources: true,
    automations: true,
    sessions: true,
    memory_stats: false,
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

      // Migrate old combo themes (e.g., "dark-blue" → theme: "dark", accent: "blue")
      for (const name of accentNames) {
        if (ui.theme === `dark-${name}`) { ui.theme = "dark"; ui.accentColor = name; break; }
        if (ui.theme === `light-${name}`) { ui.theme = "light"; ui.accentColor = name; break; }
      }

      if (!themeNames.includes(ui.theme)) ui.theme = defaultSettings.ui.theme;
      if (!(accentNames as readonly string[]).includes(ui.accentColor)) ui.accentColor = defaultSettings.ui.accentColor;
      return {
        ui,
        agent: { ...defaultSettings.agent, ...parsed.agent },
        sidebar: { ...defaultSettings.sidebar, ...parsed.sidebar },
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
    // Merge into existing file to preserve backend keys (api_key_hash, provider_keys, etc.)
    let existing: Record<string, unknown> = {};
    try {
      if (fs.existsSync(SETTINGS_FILE)) {
        const data = JSON.parse(fs.readFileSync(SETTINGS_FILE, "utf-8"));
        if (typeof data === "object" && data !== null) existing = data;
      }
    } catch {
      return; // Don't clobber a file we can't read cleanly
    }
    existing.ui = settings.ui;
    existing.agent = settings.agent;
    existing.sidebar = settings.sidebar;
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(existing, null, 2));
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
      compression_threshold: settings.agent.compressionThreshold / 100,
      max_messages: settings.agent.maxMessages,
      compression_keep_ratio: settings.agent.compressionKeepRatio / 100,
      summary_max_tokens: settings.agent.summaryMaxTokens,
      consolidation_interval: settings.agent.consolidationInterval,
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
          if (key === "compressionThreshold") agentPatch.compression_threshold = (value as number) / 100;
          if (key === "maxMessages") agentPatch.max_messages = value;
          if (key === "compressionKeepRatio") agentPatch.compression_keep_ratio = (value as number) / 100;
          if (key === "summaryMaxTokens") agentPatch.summary_max_tokens = value;
          if (key === "consolidationInterval") agentPatch.consolidation_interval = value;
          updateConfig(config, agentPatch).catch(() => {});
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
