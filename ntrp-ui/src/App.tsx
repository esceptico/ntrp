import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useRenderer } from "@opentui/react";
import type { Selection } from "@opentui/core";
import type { Message, Config } from "./types.js";
import { defaultConfig } from "./types.js";
import { colors, setTheme, themeNames, type Theme } from "./components/ui/index.js";
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
import { DimensionsProvider, useDimensions } from "./contexts/index.js";
import {
  InputArea,
  MessageDisplay,
  SettingsDialog,
  SessionPicker,
  ChoiceSelector,
  ThemePicker,
  MemoryViewer,
  SchedulesViewer,
  DashboardViewer,
  ToolChainDisplay,
  ApprovalDialog,
  ErrorBoundary,
} from "./components/index.js";
import { Sidebar } from "./components/Sidebar.js";
import { COMMANDS } from "./lib/commands.js";
import { getSkills, deleteSession, type Skill } from "./api/client.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules" | "dashboard" | "sessions";

import type { Settings } from "./hooks/useSettings.js";

interface AppContentProps {
  config: Config;
  settings: Settings;
  updateSetting: (category: keyof Settings, key: string, value: unknown) => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  setThemeByName: (name: string) => void;
  showSettings: boolean;
}

function AppContent({
  config,
  settings,
  updateSetting,
  closeSettings,
  toggleSettings,
  setThemeByName,
  showSettings
}: AppContentProps) {
  const renderer = useRenderer();

  const session = useSession(config);
  const {
    sessionId,
    sessionName,
    skipApprovals,
    serverConnected,
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
  const [showThemePicker, setShowThemePicker] = useState(false);

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
    pendingChoice,
    addMessage,
    clearMessages,
    sendMessage,
    handleChoice,
    cancelChoice,
    handleApproval,
    cancel,
    setStatus,
    resetForSessionSwitch,
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
  const { data: sidebarData, refresh: refreshSidebar } = useSidebar(config, showSidebar, messages.length);

  const isInChatMode = viewMode === "chat" && !showSettings && !showThemePicker;

  const openThemePicker = useCallback(() => setShowThemePicker(true), []);

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
    openThemePicker,
    exit: () => renderer.destroy(),
    refreshIndexStatus,
    createNewSession,
    switchSession,
    resetForSessionSwitch,
    refreshSidebar,
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
        if (isStreaming || pendingApproval || pendingChoice) return;
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

      if (isStreaming || pendingApproval || pendingChoice) {
        setMessageQueue((prev) => [...prev, trimmed]);
        return;
      }

      sendMessage(trimmed);
    },
    [isStreaming, pendingApproval, pendingChoice, sendMessage, handleCommand, addMessage, skills]
  );

  useEffect(() => {
    if (!isStreaming && !pendingApproval && !pendingChoice && messageQueue.length > 0) {
      const [firstMessage, ...rest] = messageQueue;
      setMessageQueue(rest);
      if (firstMessage) {
        sendMessage(firstMessage);
      }
    }
  }, [isStreaming, pendingApproval, pendingChoice, messageQueue, sendMessage]);

  const closeView = useCallback(() => setViewMode("chat"), []);

  const cycleSession = useCallback(async () => {
    const sessions = sidebarData.sessions;
    if (sessions.length < 2) return;
    const currentIdx = sessions.findIndex(s => s.session_id === sessionId);
    const nextIdx = (currentIdx + 1) % sessions.length;
    const target = sessions[nextIdx];
    if (!target) return;
    const result = await switchSession(target.session_id);
    if (result) {
      const historyMessages: Message[] = result.history.map((msg, i) => ({
        id: `h-${i}`,
        role: msg.role,
        content: msg.content,
      }));
      resetForSessionSwitch(historyMessages);
      refreshSidebar();
    }
  }, [sidebarData.sessions, sessionId, switchSession, resetForSessionSwitch, refreshSidebar]);

  const startNewSession = useCallback(async () => {
    const newId = await createNewSession();
    if (newId) {
      resetForSessionSwitch([]);
      refreshSidebar();
    }
  }, [createNewSession, resetForSessionSwitch, refreshSidebar]);

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
      if (key.ctrl && key.name === "n" && !isStreaming && viewMode === "chat" && !showSettings) {
        startNewSession();
        return;
      }
      if (key.name === "escape" && isStreaming) {
        cancel();
      }
      if (key.shift && key.name === "tab" && !showSettings && !isStreaming && viewMode === "chat") {
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
    [renderer, isStreaming, cancel, showSettings, viewMode, toggleSkipApprovals, cycleSession, startNewSession]
  );

  useKeypress(handleGlobalKeypress, { isActive: true });

  const hasOverlay = viewMode !== "chat" || showThemePicker;

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
            data={sidebarData}
            usage={streaming.usage}
            width={SIDEBAR_WIDTH}
            height={contentHeight}
            currentSessionId={sessionId}
            currentSessionName={sessionName}
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

          {pendingChoice && (
            <ChoiceSelector
              question={pendingChoice.question}
              options={pendingChoice.options}
              allowMultiple={pendingChoice.allowMultiple}
              onSelect={handleChoice}
              onCancel={cancelChoice}
              isActive={!pendingApproval}
            />
          )}
        </scrollbox>

        {/* Status — pinned above input */}
        {!serverConnected && (
          <box flexShrink={0}>
            <text><span fg={colors.status.error}>{BULLET} Server not connected. Run: ntrp serve</span></text>
          </box>
        )}

        {/* Input — pinned to bottom */}
        <box flexShrink={0}>
          <InputArea
            onSubmit={handleSubmit}
            disabled={!serverConnected || hasOverlay || showSettings || !!pendingApproval || !!pendingChoice}
            focus={isInChatMode && !hasOverlay && !showSettings && !pendingApproval && !pendingChoice}
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

      {/* Overlays — Dialog handles absolute positioning and dimming */}
      {viewMode === "memory" && <MemoryViewer config={config} onClose={closeView} />}
      {viewMode === "schedules" && <SchedulesViewer config={config} onClose={closeView} />}
      {viewMode === "dashboard" && <DashboardViewer config={config} onClose={closeView} />}
      {viewMode === "sessions" && (
        <SessionPicker
          config={config}
          currentSessionId={sessionId}
          onSwitch={async (targetId) => {
            const result = await switchSession(targetId);
            if (result) {
              const historyMessages: Message[] = result.history.map((msg, i) => ({
                id: `h-${i}`,
                role: msg.role,
                content: msg.content,
              }));
              resetForSessionSwitch(historyMessages);
              refreshSidebar();
            } else {
              addMessage({ role: "error", content: "Failed to switch session" } as Message);
            }
          }}
          onDelete={async (targetId) => {
            try {
              await deleteSession(config, targetId);
              if (targetId === sessionId) {
                await startNewSession();
              }
              refreshSidebar();
            } catch {
              // ignore
            }
          }}
          onNew={startNewSession}
          onClose={closeView}
        />
      )}
      {showThemePicker && (
        <ThemePicker
          current={settings.ui.theme}
          onSelect={(theme) => setThemeByName(theme)}
          onClose={() => setShowThemePicker(false)}
        />
      )}
      {showSettings && (
        <SettingsDialog
          config={config}
          serverConfig={serverConfig}
          settings={settings}
          onUpdate={updateSetting}
          onModelChange={(type: "chat" | "explore" | "memory", model: string) => updateServerConfig({ [`${type}_model`]: model })}
          onServerConfigChange={(newConfig) => updateServerConfig(newConfig)}
          onRefreshIndexStatus={refreshIndexStatus}
          onClose={closeSettings}
        />
      )}
    </box>
    </ErrorBoundary>
  );
}

function AppWithAccent({ config }: { config: Config }) {
  const { settings, updateSetting, closeSettings, toggleSettings, showSettings } = useSettings(config);

  // Sync colors before children render — setTheme mutates colors/accentColors in place
  setTheme(settings.ui.theme);

  const setThemeByName = useCallback((name: string) => {
    if (themeNames.includes(name as Theme)) {
      updateSetting("ui", "theme", name);
    }
  }, [updateSetting]);

  return (
    <AccentColorProvider accent={settings.ui.accentColor} theme={settings.ui.theme}>
      <AppContent
        config={config}
        settings={settings}
        updateSetting={updateSetting}
        closeSettings={closeSettings}
        toggleSettings={toggleSettings}
        setThemeByName={setThemeByName}
        showSettings={showSettings}
      />
    </AccentColorProvider>
  );
}

export default function App({ config = defaultConfig }: { config?: Config }) {
  return (
    <DimensionsProvider>
      <AppWithAccent config={config} />
    </DimensionsProvider>
  );
}
