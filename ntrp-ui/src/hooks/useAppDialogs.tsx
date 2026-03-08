import { useCallback } from "react";
import type { Config, Message } from "../types.js";
import type { ServerConfig, HistoryMessage } from "../api/client.js";
import type { AccentColor, Theme } from "../components/ui/index.js";
import type { Settings } from "./useSettings.js";
import { deleteSession, listSessions, restoreSession, permanentlyDeleteSession } from "../api/client.js";
import { convertHistoryToMessages } from "../lib/history.js";
import {
  SessionPicker,
  ModelPicker,
  ThemePicker,
} from "../components/index.js";
import { ProviderOnboarding } from "../components/ProviderOnboarding.js";

interface DialogHandle {
  open: (element: React.ReactNode) => void;
  close: () => void;
}

interface AppDialogsParams {
  config: Config;
  sessionId: string | null;
  serverConfig: ServerConfig | null;
  dialog: DialogHandle;
  switchSession: (id: string) => Promise<{ history: HistoryMessage[] } | null>;
  switchToSession: (id: string, history?: Message[]) => void;
  deleteSessionState: (id: string) => void;
  addMessage: (msg: Message) => void;
  refreshSidebar: () => void;
  startNewSession: () => Promise<void>;
  updateServerConfig: (patch: Partial<ServerConfig>) => void;
  refreshIndexStatus: () => Promise<void>;
  setThemeByName: (name: string) => void;
  updateSetting: (category: keyof Settings, key: string, value: unknown) => void;
  theme: Theme;
  accentColor: AccentColor;
}

export function useAppDialogs({
  config,
  sessionId,
  serverConfig,
  dialog,
  switchSession,
  switchToSession,
  deleteSessionState,
  addMessage,
  refreshSidebar,
  startNewSession,
  updateServerConfig,
  refreshIndexStatus,
  setThemeByName,
  updateSetting,
  theme,
  accentColor,
}: AppDialogsParams) {
  const openDialog = useCallback((id: string) => {
    switch (id) {
      case "sessions":
        dialog.open(
          <SessionPicker
            config={config}
            currentSessionId={sessionId}
            onSwitch={async (targetId) => {
              const result = await switchSession(targetId);
              if (result) {
                switchToSession(targetId, convertHistoryToMessages(result.history));
                refreshSidebar();
              } else {
                addMessage({ role: "error", content: "Failed to switch session" } as Message);
              }
            }}
            onDelete={async (targetId) => {
              try {
                deleteSessionState(targetId);
                await deleteSession(config, targetId);
                if (targetId === sessionId) {
                  const { sessions } = await listSessions(config);
                  const next = sessions.find(s => s.session_id !== targetId);
                  if (next) {
                    const result = await switchSession(next.session_id);
                    if (result) {
                      switchToSession(next.session_id, convertHistoryToMessages(result.history));
                    } else {
                      await startNewSession();
                    }
                  } else {
                    await startNewSession();
                  }
                }
                refreshSidebar();
              } catch {}
            }}
            onRestore={async (targetId) => {
              try { await restoreSession(config, targetId); refreshSidebar(); } catch {}
            }}
            onPermanentDelete={async (targetId) => {
              try { await permanentlyDeleteSession(config, targetId); } catch {}
            }}
            onNew={startNewSession}
            onClose={() => dialog.close()}
          />
        );
        break;
      case "models":
        dialog.open(
          <ModelPicker
            config={config}
            serverConfig={serverConfig}
            onModelChange={(type, model) => updateServerConfig({ [`${type}_model`]: model })}
            onServerConfigChange={(newConfig) => updateServerConfig(newConfig)}
            onRefreshIndexStatus={refreshIndexStatus}
            onClose={() => dialog.close()}
          />
        );
        break;
      case "providers":
        dialog.open(
          <ProviderOnboarding config={config} closable onClose={() => dialog.close()} onDone={() => dialog.close()} />
        );
        break;
      case "theme":
        dialog.open(
          <ThemePicker
            currentTheme={theme}
            currentAccent={accentColor}
            onSelect={(selectedTheme, selectedAccent) => {
              setThemeByName(selectedTheme);
              if (selectedAccent !== accentColor) updateSetting("ui", "accentColor", selectedAccent);
              dialog.close();
            }}
            onClose={() => dialog.close()}
          />
        );
        break;
    }
  }, [config, sessionId, serverConfig, theme, accentColor, dialog, switchSession, switchToSession, deleteSessionState, refreshSidebar, addMessage, startNewSession, updateServerConfig, refreshIndexStatus, setThemeByName, updateSetting]);

  return { openDialog };
}
