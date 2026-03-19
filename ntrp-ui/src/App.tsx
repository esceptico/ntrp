import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useRenderer } from "@opentui/react";
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { Selection, ScrollBoxRenderable, Renderable } from "@opentui/core";
import type { Message, Config } from "./types.js";
import type { ImageBlock } from "./api/chat.js";
import { colors, setTheme, useThemeVersion, themeNames, type Theme } from "./components/ui/index.js";
import { BULLET } from "./lib/constants.js";
import { queryClient } from "./lib/queryClient.js";
import {
  useSettings,
  useKeypress,
  useCommands,
  useSession,
  useStreaming,
  useSidebar,
  useMessageQueue,
  useAppDialogs,
  AccentColorProvider,
  type Key,
} from "./hooks/index.js";
import { convertHistoryToMessages } from "./lib/history.js";
import { DimensionsProvider, useDimensions, DialogProvider, useDialog } from "./contexts/index.js";
import {
  InputArea,
  MessageDisplay,
  SettingsDialog,
  MemoryViewer,
  AutomationsViewer,
  ToolChainDisplay,
  ApprovalDialog,
  ErrorBoundary,
} from "./components/index.js";
import { Setup } from "./components/Setup.js";
import { ProviderOnboarding } from "./components/ProviderOnboarding.js";
import { Sidebar } from "./components/sidebar/index.js";
import { Markdown } from "./components/Markdown.js";
import { COMMANDS } from "./lib/commands.js";
import { setApiKey } from "./api/fetch.js";
import { getSkills, type Skill } from "./api/client.js";

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

  const initialMessages = useMemo(() => convertHistoryToMessages(history), [history]);

  const [viewMode, setViewMode] = useState<ViewMode>("chat");
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const dialog = useDialog();

  const { data: skillsData } = useQuery({
    queryKey: ["skills", config.serverUrl],
    queryFn: () => getSkills(config),
    enabled: serverConnected,
  });
  const skills = skillsData?.skills ?? [];

  const streaming = useStreaming({
    config,
    sessionId,
    skipApprovals,
    streaming: settings.ui.streaming,
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
    background,
    revert,
    revertAndResend,
    setStatus,
    switchToSession,
    deleteSessionState,
    backgroundTaskCount,
    pendingText,
  } = streaming;

  const { messageQueue, enqueue, clearQueue } = useMessageQueue(isStreaming, pendingApproval, sendMessage);

  const [prefill, setPrefill] = useState<string | null>(null);

  const [copiedFlash, setCopiedFlash] = useState(false);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onSelection = (selection: Selection) => {
      const text = selection.getSelectedText();
      if (!text) return;
      renderer.copyToClipboardOSC52(text);
      if (process.platform === "darwin") {
        Bun.spawn(["pbcopy"], { stdin: new TextEncoder().encode(text) });
      }
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      setCopiedFlash(true);
      copiedTimerRef.current = setTimeout(() => setCopiedFlash(false), 1500);
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
  const { data: sidebarData, refresh: refreshSidebar } = useSidebar(config, showSidebar, messages.length, sessionId, settings.sidebar);

  const isInChatMode = viewMode === "chat" && !showSettings && !dialog.isOpen;

  const startNewSession = useCallback(async () => {
    const newId = await createNewSession();
    if (newId) {
      cycleIdRef.current = null;
      clearQueue();
      switchToSession(newId, []);
      refreshSidebar();
    }
  }, [createNewSession, switchToSession, refreshSidebar, clearQueue]);

  const { openDialog } = useAppDialogs({
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
    theme: settings.ui.theme,
    accentColor: settings.ui.accentColor,
    transparentBg: settings.ui.transparentBg,
  });

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
    revert,
    setInputText: setPrefill,
    deleteSessionState,
    refreshSidebar,
    logout,
  });

  const allCommands = useMemo(() => [
    ...COMMANDS,
    ...skills.map(s => ({ name: s.name, description: `(skill) ${s.description}` })),
  ], [skills]);

  const handleSubmit = useCallback(
    async (value: string, images?: ImageBlock[]) => {
      const trimmed = value.trim();
      if (!trimmed && !images?.length) return;

      if (trimmed.startsWith("/")) {
        if (pendingApproval) return;
        const handled = await handleCommand(trimmed);
        if (handled) return;
        const cmdName = trimmed.slice(1).split(" ")[0];
        if (skills.some(s => s.name === cmdName)) {
          sendMessage(trimmed, images);
        } else {
          addMessage({ role: "error", content: `Unknown command: ${trimmed}` });
        }
        return;
      }

      if (pendingApproval) {
        enqueue(trimmed, images);
        return;
      }

      sendMessage(trimmed, images);
    },
    [pendingApproval, sendMessage, handleCommand, addMessage, skills, enqueue]
  );

  const handleEditSubmit = useCallback(
    (message: string, turns: number) => {
      revertAndResend(message, turns);
    },
    [revertAndResend]
  );

  const closeView = useCallback(() => setViewMode("chat"), []);

  const chatScrollRef = useRef<ScrollBoxRenderable | null>(null);
  const messageRefsMap = useRef<Map<string, Renderable>>(new Map());

  useEffect(() => {
    const scroll = chatScrollRef.current;
    if (scroll) setTimeout(() => scroll.scrollTo(scroll.scrollHeight), 0);
  }, [sessionId]);

  useEffect(() => {
    if (!editingMessageId) return;
    const scroll = chatScrollRef.current;
    const el = messageRefsMap.current.get(editingMessageId);
    if (!scroll || !el) return;
    const offset = el.y - scroll.content.y;
    scroll.scrollTo(offset);
  }, [editingMessageId]);

  const cycleIdRef = useRef<string | null>(null);

  const cycleSession = useCallback(() => {
    const sessions = sidebarData.sessions;
    if (sessions.length < 2) return;
    const currentId = cycleIdRef.current ?? sessionId;
    const currentIdx = sessions.findIndex(s => s.session_id === currentId);
    const nextIdx = (currentIdx + 1) % sessions.length;
    const target = sessions[nextIdx];
    if (!target) return;

    cycleIdRef.current = target.session_id;
    clearQueue();
    switchToSession(target.session_id);

    switchSession(target.session_id).then((result) => {
      if (cycleIdRef.current !== target.session_id) return;
      if (result) {
        switchToSession(target.session_id, convertHistoryToMessages(result.history));
      }
    });
  }, [sessionId, sidebarData.sessions, switchSession, switchToSession, clearQueue]);

  const handleSessionClick = useCallback((targetId: string) => {
    if (targetId === sessionId) return;
    clearQueue();
    switchToSession(targetId);
    switchSession(targetId).then((result) => {
      if (result) {
        switchToSession(targetId, convertHistoryToMessages(result.history));
      }
    });
  }, [sessionId, switchSession, switchToSession, clearQueue]);

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
      if (key.ctrl && key.sequence === "," && viewMode === "chat" && !dialog.isOpen) {
        toggleSettings();
        return;
      }
      if (key.ctrl && key.name === "n" && viewMode === "chat" && !showSettings && !dialog.isOpen) {
        startNewSession();
        return;
      }
      if (key.name === "escape" && isStreaming && !dialog.isOpen) {
        cancel();
        return;
      }
      if (key.ctrl && key.name === "o" && isStreaming && !dialog.isOpen) {
        background();
        return;
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
    [renderer, isStreaming, pendingApproval, cancel, background, showSettings, viewMode, dialog.isOpen, toggleSkipApprovals, toggleSettings, cycleSession, startNewSession]
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
            sections={settings.sidebar}
            onSessionClick={handleSessionClick}
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
        <scrollbox ref={(r: ScrollBoxRenderable) => { chatScrollRef.current = r; }} flexGrow={1} stickyScroll={true} stickyStart="bottom" style={{ scrollbarOptions: { visible: false } }}>
          {messages.map((item, index) => {
            const prevItem = messages[index - 1];
            const isToolMessage = item.role === "tool" || item.role === "tool_chain";
            const prevIsToolMessage = prevItem &&
              (prevItem.role === "tool" || prevItem.role === "tool_chain");
            const needsMargin = index > 0 && !(isToolMessage && prevIsToolMessage);

            return (
              <box
                key={item.id}
                marginTop={needsMargin ? 1 : 0}
                ref={item.id ? (r: Renderable) => {
                  if (r) messageRefsMap.current.set(item.id!, r);
                  else messageRefsMap.current.delete(item.id!);
                } : undefined}
              >
                <MessageDisplay msg={item} editing={item.id === editingMessageId} />
              </box>
            );
          })}

          {pendingText.trimStart() && (
            <box marginTop={1} paddingLeft={3} overflow="hidden">
              <box flexGrow={1} flexDirection="column" overflow="hidden">
                <Markdown streaming>{pendingText.trimStart()}</Markdown>
              </box>
            </box>
          )}

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
            <text><span fg={colors.status.error}>{BULLET} Server not connected. Reconnecting… </span><span fg={colors.text.muted}>(Ctrl+, to change)</span></text>
          </box>
        )}

        {/* Input — pinned to bottom */}
        <box flexShrink={0}>
          <InputArea
            onSubmit={handleSubmit}
            onEditSubmit={handleEditSubmit}
            disabled={!serverConnected || hasOverlay || showSettings || !!pendingApproval}
            focus={isInChatMode && !hasOverlay && !showSettings && !pendingApproval}
            isStreaming={isStreaming}
            status={status}
            commands={allCommands}
            messages={messages}
            onEditingChange={setEditingMessageId}
            queueCount={messageQueue.length}
            skipApprovals={skipApprovals}
            chatModel={serverConfig?.chat_model}
            sessionName={sessionName}
            indexStatus={indexStatus}
            copiedFlash={copiedFlash}
            backgroundTaskCount={backgroundTaskCount}
            prefill={prefill}
            onPrefillConsumed={() => setPrefill(null)}
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
  setTheme(settings.ui.theme, settings.ui.accentColor, settings.ui.transparentBg);

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

  return (
    <QueryClientProvider client={queryClient}>
      <DimensionsProvider>
        {config.needsSetup ? (
          <Setup
            initialServerUrl={config.serverUrl}
            onConnect={handleConnect}
          />
        ) : config.needsProvider ? (
          <ProviderOnboarding
            config={config}
            onClose={() => {}}
            onDone={() => setConfig(c => ({ ...c, needsProvider: false }))}
          />
        ) : (
          <AppWithAccent config={config} logout={handleLogout} onServerChange={handleConnect} />
        )}
      </DimensionsProvider>
    </QueryClientProvider>
  );
}
