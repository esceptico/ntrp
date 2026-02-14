import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useRenderer } from "@opentui/react";
import type { Selection } from "@opentui/core";
import type { Message, Config } from "./types.js";
import { defaultConfig } from "./types.js";
import { colors } from "./components/ui/colors.js";
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
  ChoiceSelector,
  MemoryViewer,
  SchedulesViewer,
  DashboardViewer,
  ToolChainDisplay,
  ApprovalDialog,
  ErrorBoundary,
} from "./components/index.js";
import { Sidebar } from "./components/Sidebar.js";
import { COMMANDS } from "./lib/commands.js";
import { getSkills, type Skill } from "./api/client.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules" | "dashboard";

import type { Settings } from "./hooks/useSettings.js";

interface AppContentProps {
  config: Config;
  settings: Settings;
  updateSetting: (category: keyof Settings, key: string, value: unknown) => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  showSettings: boolean;
}

function AppContent({
  config,
  settings,
  updateSetting,
  closeSettings,
  toggleSettings,
  showSettings
}: AppContentProps) {
  const renderer = useRenderer();

  const session = useSession(config);
  const {
    sessionId,
    skipApprovals,
    serverConnected,
    serverConfig,
    indexStatus,
    history,
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
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

  const isInChatMode = viewMode === "chat" && !showSettings;

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
    exit: () => renderer.destroy(),
    refreshIndexStatus,
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

  const handleGlobalKeypress = useCallback(
    async (key: Key) => {
      if (key.ctrl && key.name === "c") {
        renderer.destroy();
      }
      if (key.ctrl && key.name === "l") {
        setSidebarVisible(v => !v);
        return;
      }
      if (key.name === "escape" && isStreaming) {
        cancel();
      }
      if (key.shift && key.name === "tab" && !showSettings) {
        toggleSkipApprovals();
      }
    },
    [renderer, isStreaming, cancel, toggleSkipApprovals, showSettings]
  );

  useKeypress(handleGlobalKeypress, { isActive: true });

  const { width, height } = useDimensions();
  const hasOverlay = viewMode !== "chat";

  const SIDEBAR_WIDTH = 32;
  const showSidebar = sidebarVisible && width >= 94 && serverConnected;
  const sidebarData = useSidebar(config, showSidebar, messages.length);

  const contentHeight = height - 2; // paddingTop + paddingBottom
  const mainPadding = 4; // paddingLeft(2) + paddingRight(2)
  const sidebarTotal = showSidebar ? SIDEBAR_WIDTH + 1 : 0; // sidebar + divider
  const mainWidth = Math.max(0, width - sidebarTotal - mainPadding);

  return (
    <ErrorBoundary>
    <box flexDirection="row" width={width} height={height} paddingTop={1} paddingBottom={1} backgroundColor={colors.background.base}>
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
                <MessageDisplay
                  msg={item}
                  renderMarkdown={settings.ui.renderMarkdown}
                />
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
            indexStatus={indexStatus}
            copiedFlash={copiedFlash}
          />
        </box>
      </DimensionsProvider>
      </box>

      {/* Sidebar */}
      {showSidebar && (
        <>
          <box width={1} height={contentHeight} flexShrink={0} flexDirection="column">
            {Array.from({ length: contentHeight }).map((_, i) => (
              <text key={i}><span fg={colors.divider}>{"\u2502"}</span></text>
            ))}
          </box>
          <Sidebar
            serverConfig={serverConfig}
            data={sidebarData}
            width={SIDEBAR_WIDTH}
            height={contentHeight}
          />
        </>
      )}

      {/* Overlays — Dialog handles absolute positioning and dimming */}
      {viewMode === "memory" && <MemoryViewer config={config} onClose={closeView} />}
      {viewMode === "schedules" && <SchedulesViewer config={config} onClose={closeView} />}
      {viewMode === "dashboard" && <DashboardViewer config={config} onClose={closeView} />}
      {showSettings && (
        <SettingsDialog
          config={config}
          serverConfig={serverConfig}
          settings={settings}
          onUpdate={updateSetting}
          onModelChange={(type: "chat" | "explore" | "memory", model: string) => updateServerConfig({ [`${type}_model`]: model })}
          onServerConfigChange={(newConfig) => updateServerConfig(newConfig)}
          onClose={closeSettings}
        />
      )}
    </box>
    </ErrorBoundary>
  );
}

function AppWithAccent({ config }: { config: Config }) {
  const { settings, updateSetting, closeSettings, toggleSettings, showSettings } = useSettings(config);

  return (
    <AccentColorProvider accent={settings.ui.accentColor}>
      <AppContent
        config={config}
        settings={settings}
        updateSetting={updateSetting}
        closeSettings={closeSettings}
        toggleSettings={toggleSettings}
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
