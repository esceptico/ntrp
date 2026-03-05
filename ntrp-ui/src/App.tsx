import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useRenderer } from "@opentui/react";
import type { Selection } from "@opentui/core";
import type { Message, Config } from "./types.js";
import { colors, setTheme, useThemeVersion, themeNames, type Theme } from "./components/ui/index.js";
import { BULLET } from "./lib/constants.js";
import {
  useSettings,
  useKeypress,
  useCommands,
  useSession,
  useStreaming,
  useSidebar,
  AccentColorProvider,
  type Key,
} from "./hooks/index.js";
import { DimensionsProvider, useDimensions, DialogProvider, useDialog } from "./contexts/index.js";
import {
  InputArea,
  MessageDisplay,
  SettingsDialog,
  SessionPicker,
  MemoryViewer,
  AutomationsViewer,
  ToolChainDisplay,
  ApprovalDialog,
  ErrorBoundary,
  ModelPicker,
  ThemePicker,
} from "./components/index.js";
import { Setup } from "./components/Setup.js";
import { ProviderOnboarding } from "./components/ProviderOnboarding.js";
import { Sidebar } from "./components/sidebar/index.js";
import { COMMANDS } from "./lib/commands.js";
import { setApiKey } from "./api/fetch.js";
import { getSkills, deleteSession, listSessions, restoreSession, permanentlyDeleteSession, type Skill } from "./api/client.js";

type ViewMode = "chat" | "memory" | "automations";

import type { Settings } from "./hooks/useSettings.js";

interface AppContentProps {
  config: Config;
  settings: Settings;
  updateSetting: (category: keyof Settings, key: string, value: unknown) => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  setThemeByName: (name: string) => void;
  showSettings: boolean;
  logout: () => void;
  onServerChange: (config: Config) => void;
}

function AppContent({
  config,
  settings,
  updateSetting,
  closeSettings,
  toggleSettings,
  setThemeByName,
  showSettings,
  logout,
  onServerChange
}: AppContentProps) {
  const renderer = useRenderer();
  useThemeVersion();

  const session = useSession(config);
  const {
    sessionId,
    sessionName,
    skipApprovals,
    serverConnected,
    serverVersion,
    serverConfig,
    indexStatus,
    history,
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
    switchSession,
    createNewSession,
  } = session;

  const initialMessages = useMemo(() =>
    history.map((msg, i): Message => ({
      id: `h-${i}`,
      role: msg.role,
      content: msg.content,
    })),
    [history]
  );

  const [viewMode, setViewMode] = useState<ViewMode>("chat");
  const [messageQueue, setMessageQueue] = useState<string[]>([]);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const dialog = useDialog();

  const [skills, setSkills] = useState<Skill[]>([]);
  useEffect(() => {
    getSkills(config).then(r => setSkills(r.skills)).catch(() => {});
  }, [config]);

  const streaming = useStreaming({
    config,
    sessionId,
    skipApprovals,
    onSessionInfo: updateSessionInfo,
    initialMessages,
  });
  const {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    sessionStates,
    addMessage,
    clearMessages,
    sendMessage,
    handleApproval,
    cancel,
    setStatus,
    switchToSession,
    deleteSessionState,
  } = streaming;

  const [copiedFlash, setCopiedFlash] = useState(false);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onSelection = (selection: Selection) => {
      const text = selection.getSelectedText();
      if (text) {
        renderer.copyToClipboardOSC52(text);
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        setCopiedFlash(true);
        copiedTimerRef.current = setTimeout(() => setCopiedFlash(false), 1500);
      }
    };
    renderer.on("selection", onSelection);
    return () => {
      renderer.off("selection", onSelection);
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, [renderer]);

  const { width, height } = useDimensions();
  const SIDEBAR_WIDTH = 32;
  const showSidebar = sidebarVisible && width >= 94 && serverConnected;
  const { data: sidebarData, refresh: refreshSidebar } = useSidebar(config, showSidebar, messages.length, sessionId);

  const isInChatMode = viewMode === "chat" && !showSettings && !dialog.isOpen;

  const startNewSession = useCallback(async () => {
    const newId = await createNewSession();
    if (newId) {
      setMessageQueue([]);
      switchToSession(newId, []);
      refreshSidebar();
    }
  }, [createNewSession, switchToSession, refreshSidebar]);

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
                const historyMessages: Message[] = result.history.map((msg, i) => ({
                  id: `h-${i}`, role: msg.role, content: msg.content,
                }));
                switchToSession(targetId, historyMessages);
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
                      switchToSession(next.session_id, result.history.map((msg, i) => ({
                        id: `h-${i}`, role: msg.role, content: msg.content,
                      })));
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
            currentTheme={settings.ui.theme}
            currentAccent={settings.ui.accentColor}
            onSelect={(theme, accent) => {
              setThemeByName(theme);
              if (accent !== settings.ui.accentColor) updateSetting("ui", "accentColor", accent);
              dialog.close();
            }}
            onClose={() => dialog.close()}
          />
        );
        break;
    }
  }, [config, sessionId, serverConfig, settings.ui.theme, settings.ui.accentColor, dialog, switchSession, switchToSession, deleteSessionState, refreshSidebar, addMessage, startNewSession, updateServerConfig, refreshIndexStatus, setThemeByName, updateSetting]);

  const { handleCommand } = useCommands({
    config,
    sessionId,
    messages,
    setViewMode,
    updateSessionInfo,
    addMessage: (msg) => addMessage(msg as Message),
    clearMessages,
    sendMessage,
    setStatus,
    toggleSettings,
    openDialog,
    exit: () => renderer.destroy(),
    refreshIndexStatus,
    createNewSession,
    switchSession,
    switchToSession,
    deleteSessionState,
    refreshSidebar,
    logout,
  });

  const allCommands = useMemo(() => [
    ...COMMANDS,
    ...skills.map(s => ({ name: s.name, description: `(skill) ${s.description}` })),
  ], [skills]);

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;

      if (trimmed.startsWith("/")) {
        if (pendingApproval) return;
        const handled = await handleCommand(trimmed);
        if (handled) return;
        const cmdName = trimmed.slice(1).split(" ")[0];
        if (skills.some(s => s.name === cmdName)) {
          sendMessage(trimmed);
        } else {
          addMessage({ role: "error", content: `Unknown command: ${trimmed}` });
        }
        return;
      }

      if (isStreaming || pendingApproval) {
        setMessageQueue((prev) => [...prev, trimmed]);
        return;
      }

      sendMessage(trimmed);
    },
    [isStreaming, pendingApproval, sendMessage, handleCommand, addMessage, skills]
  );

  useEffect(() => {
    if (!isStreaming && !pendingApproval && messageQueue.length > 0) {
      const [firstMessage, ...rest] = messageQueue;
      setMessageQueue(rest);
      if (firstMessage) {
        sendMessage(firstMessage);
      }
    }
  }, [isStreaming, pendingApproval, messageQueue, sendMessage]);

  const closeView = useCallback(() => setViewMode("chat"), []);

  const isCyclingRef = useRef(false);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const cycleSession = useCallback(async () => {
    if (isCyclingRef.current) return;
    const sessions = sidebarData.sessions;
    if (sessions.length < 2) return;
    const currentIdx = sessions.findIndex(s => s.session_id === sessionId);
    const nextIdx = (currentIdx + 1) % sessions.length;
    const target = sessions[nextIdx];
    if (!target) return;

    isCyclingRef.current = true;
    setMessageQueue([]);
    switchToSession(target.session_id);

    try {
      const result = await switchSession(target.session_id);
      if (result) {
        switchToSession(target.session_id, result.history.map((msg, i) => ({
          id: `h-${i}`, role: msg.role, content: msg.content,
        })));
      } else {
        switchToSession(sessionIdRef.current!);
      }
    } finally {
      isCyclingRef.current = false;
    }
  }, [sidebarData.sessions, sessionId, switchSession, switchToSession]);

  const tabPendingRef = useRef(false);
  const tabTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleGlobalKeypress = useCallback(
    async (key: Key) => {
      if (key.ctrl && key.name === "c") {
        renderer.destroy();
      }
      if (key.ctrl && key.name === "l") {
        setSidebarVisible(v => !v);
        return;
      }
      if (key.ctrl && key.name === "n" && viewMode === "chat" && !showSettings && !dialog.isOpen) {
        startNewSession();
        return;
      }
      if (key.name === "escape" && isStreaming && !dialog.isOpen) {
        cancel();
      }
      if (key.shift && key.name === "tab" && !showSettings && viewMode === "chat" && !dialog.isOpen && !pendingApproval) {
        cycleSession();
        return;
      }
      if (key.name === "tab" && !key.shift && !key.ctrl && !key.meta && !showSettings) {
        if (tabPendingRef.current) {
          tabPendingRef.current = false;
          if (tabTimeoutRef.current) clearTimeout(tabTimeoutRef.current);
          toggleSkipApprovals();
        } else {
          tabPendingRef.current = true;
          if (tabTimeoutRef.current) clearTimeout(tabTimeoutRef.current);
          tabTimeoutRef.current = setTimeout(() => {
            tabPendingRef.current = false;
          }, 500);
        }
        return;
      }
    },
    [renderer, isStreaming, pendingApproval, cancel, showSettings, viewMode, dialog.isOpen, toggleSkipApprovals, cycleSession, startNewSession]
  );

  useKeypress(handleGlobalKeypress, { isActive: true });

  const hasOverlay = viewMode !== "chat" || dialog.isOpen;

  const contentHeight = height - 2; // paddingTop + paddingBottom
  const mainPadding = 4; // paddingLeft(2) + paddingRight(2)
  const sidebarTotal = showSidebar ? SIDEBAR_WIDTH + 1 : 0; // sidebar + divider
  const mainWidth = Math.max(0, width - sidebarTotal - mainPadding);

  return (
    <ErrorBoundary>
    <box flexDirection="row" width={width} height={height} paddingTop={1} paddingBottom={1} backgroundColor={colors.background.base}>
      {/* Sidebar */}
      {showSidebar && (
        <>
          <Sidebar
            serverConfig={serverConfig}
            serverVersion={serverVersion}
            serverUrl={config.serverUrl}
            data={sidebarData}
            usage={streaming.usage}
            width={SIDEBAR_WIDTH}
            height={contentHeight}
            currentSessionId={sessionId}
            currentSessionName={sessionName}
            sessionStates={sessionStates}
          />
          <box width={1} height={contentHeight} flexShrink={0} flexDirection="column">
            {Array.from({ length: contentHeight }).map((_, i) => (
              <text key={i}><span fg={colors.divider}>{"\u2502"}</span></text>
            ))}
          </box>
        </>
      )}

      {/* Main content */}
      <box flexDirection="column" flexGrow={1} paddingLeft={2} paddingRight={2} gap={1}>
      <DimensionsProvider padding={0} width={mainWidth}>
        {/* Scrollable message area */}
        <scrollbox flexGrow={1} stickyScroll={true} stickyStart="bottom" style={{ scrollbarOptions: { visible: false } }}>
          {messages.map((item, index) => {
            const prevItem = messages[index - 1];
            const isToolMessage = item.role === "tool" || item.role === "tool_chain";
            const prevIsToolMessage = prevItem &&
              (prevItem.role === "tool" || prevItem.role === "tool_chain");
            const needsMargin = index > 0 && !(isToolMessage && prevIsToolMessage);

            return (
              <box key={item.id} marginTop={needsMargin ? 1 : 0}>
                <MessageDisplay msg={item} />
              </box>
            );
          })}

          {toolChain.length > 0 && (
            <box marginTop={messages[messages.length - 1]?.role === "user" ? 1 : 0}>
              <ToolChainDisplay items={toolChain} />
            </box>
          )}

          {pendingApproval && (
            <ApprovalDialog
              approval={pendingApproval}
              onResult={handleApproval}
            />
          )}

        </scrollbox>

        {/* Status — pinned above input */}
        {!serverConnected && (
          <box flexShrink={0}>
            <text><span fg={colors.status.error}>{BULLET} Server not connected. Reconnecting...</span></text>
          </box>
        )}

        {/* Input — pinned to bottom */}
        <box flexShrink={0}>
          <InputArea
            onSubmit={handleSubmit}
            disabled={!serverConnected || hasOverlay || showSettings || !!pendingApproval}
            focus={isInChatMode && !hasOverlay && !showSettings && !pendingApproval}
            isStreaming={isStreaming}
            status={status}
            commands={allCommands}
            queueCount={messageQueue.length}
            skipApprovals={skipApprovals}
            chatModel={serverConfig?.chat_model}
            sessionName={sessionName}
            indexStatus={indexStatus}
            copiedFlash={copiedFlash}
          />
        </box>
      </DimensionsProvider>
      </box>

      {/* Overlays */}
      {viewMode === "memory" && <MemoryViewer config={config} onClose={closeView} />}
      {viewMode === "automations" && <AutomationsViewer config={config} onClose={closeView} />}
      {showSettings && (
        <SettingsDialog
          config={config}
          serverConfig={serverConfig}
          settings={settings}
          onUpdate={updateSetting}
          onServerConfigChange={(newConfig) => updateServerConfig(newConfig)}
          onRefreshIndexStatus={refreshIndexStatus}
          onClose={closeSettings}
          onServerCredentialsChange={onServerChange}
        />
      )}
    </box>
    </ErrorBoundary>
  );
}

function AppWithAccent({ config, logout, onServerChange }: { config: Config; logout: () => void; onServerChange: (config: Config) => void }) {
  const { settings, updateSetting, closeSettings, toggleSettings, showSettings } = useSettings(config);

  // Sync colors before children render — setTheme mutates colors/currentAccent in place
  setTheme(settings.ui.theme, settings.ui.accentColor);

  const setThemeByName = useCallback((name: string) => {
    if (themeNames.includes(name as Theme)) {
      updateSetting("ui", "theme", name);
    }
  }, [updateSetting]);

  return (
    <AccentColorProvider>
      <DialogProvider>
        <AppContent
          config={config}
          settings={settings}
          updateSetting={updateSetting}
          closeSettings={closeSettings}
          toggleSettings={toggleSettings}
          setThemeByName={setThemeByName}
          showSettings={showSettings}
          logout={logout}
          onServerChange={onServerChange}
        />
      </DialogProvider>
    </AccentColorProvider>
  );
}

export default function App({ config: initialConfig }: { config: Config }) {
  const [config, setConfig] = useState(initialConfig);

  const handleConnect = useCallback((newConfig: Config) => {
    setApiKey(newConfig.apiKey);
    setConfig(newConfig);
  }, []);

  const handleLogout = useCallback(() => {
    setApiKey("");
    setConfig((c) => ({ ...c, apiKey: "", needsSetup: true }));
  }, []);

  if (config.needsSetup) {
    return (
      <DimensionsProvider>
        <Setup
          initialServerUrl={config.serverUrl}
          onConnect={handleConnect}
        />
      </DimensionsProvider>
    );
  }

  if (config.needsProvider) {
    return (
      <DimensionsProvider>
        <ProviderOnboarding
          config={config}
          onClose={() => {}}
          onDone={() => setConfig(c => ({ ...c, needsProvider: false }))}
        />
      </DimensionsProvider>
    );
  }

  return (
    <DimensionsProvider>
      <AppWithAccent config={config} logout={handleLogout} onServerChange={handleConnect} />
    </DimensionsProvider>
  );
}
