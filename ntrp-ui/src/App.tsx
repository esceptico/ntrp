import React, { useState, useCallback, useEffect } from "react";
import { Box, Text, useApp, Static } from "ink";
import type { Message, Config } from "./types.js";
import { defaultConfig } from "./types.js";
import { colors } from "./components/ui/colors.js";
import { BULLET } from "./lib/constants.js";
import {
  useSettings,
  KeypressProvider,
  useKeypress,
  useCommands,
  useSession,
  useStreaming,
  AccentColorProvider,
  type Key,
} from "./hooks/index.js";
import { DimensionsProvider } from "./contexts/index.js";
import {
  InputArea,
  MessageDisplay,
  SettingsDialog,
  ChoiceSelector,
  MemoryViewer,
  SchedulesViewer,
  ToolChainDisplay,
  Welcome,
  ThinkingIndicator,
  ApprovalDialog,
  ErrorBoundary,
} from "./components/index.js";
import { COMMANDS } from "./lib/commands.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules";

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
  const { exit } = useApp();

  // Session management (server connection, config, index status)
  const session = useSession(config);
  const {
    sessionId,
    skipApprovals,
    serverConnected,
    serverConfig,
    indexStatus,
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
  } = session;

  // Local state for UI
  const [viewMode, setViewMode] = useState<ViewMode>("chat");
  const [messageQueue, setMessageQueue] = useState<string[]>([]);
  // Track if welcome was shown (don't show again after clear)
  const [welcomeShown, setWelcomeShown] = useState(false);

  // Streaming (messages, tool chain, approvals)
  const streaming = useStreaming({
    config,
    sessionId,
    skipApprovals,
    onSessionInfo: updateSessionInfo,
  });
  const {
    messages,
    isStreaming,
    status,
    toolChain,
    pendingApproval,
    pendingChoice,
    clearCount,
    addMessage,
    clearMessages,
    sendMessage,
    handleChoice,
    cancelChoice,
    handleApproval,
    cancel,
  } = streaming;

  // Only handle input when in chat mode (not when viewer is open)
  const isInChatMode = viewMode === "chat" && !showSettings;

  // Command handler via registry pattern
  const { handleCommand } = useCommands({
    config,
    sessionId,
    messages,
    setViewMode,
    updateSessionInfo,
    addMessage: (msg) => addMessage(msg as Message),
    clearMessages,
    clearMessageQueue: () => setMessageQueue([]),
    sendMessage,
    toggleSettings,
    exit,
    refreshIndexStatus,
  });

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;

      // Handle commands immediately (don't queue)
      if (trimmed.startsWith("/")) {
        if (isStreaming || pendingApproval || pendingChoice) return; // Block commands during streaming
        const handled = await handleCommand(trimmed);
        if (handled) return;
        addMessage({ role: "error", content: `Unknown command: ${trimmed}` });
        return;
      }

      // Queue messages during streaming
      if (isStreaming || pendingApproval || pendingChoice) {
        setMessageQueue((prev) => [...prev, trimmed]);
        return;
      }

      sendMessage(trimmed);
    },
    [isStreaming, pendingApproval, pendingChoice, sendMessage, handleCommand, addMessage]
  );

  // Process queued messages when streaming ends
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

  // Global keypress handler for exit, cancel, and skip approvals toggle
  // Scrolling uses native terminal scrollback
  const handleGlobalKeypress = useCallback(
    async (key: Key) => {
      if (key.ctrl && key.name === "c") {
        exit();
      }
      // Escape cancels the current run
      if (key.name === "escape" && isStreaming) {
        cancel();
      }
      // Shift+Tab toggles skip approvals mode (guard: not in settings overlay)
      if (key.shift && key.name === "tab" && !showSettings) {
        toggleSkipApprovals();
      }
    },
    [exit, isStreaming, cancel, toggleSkipApprovals, showSettings]
  );

  useKeypress(handleGlobalKeypress, { isActive: true });

  // All overlays render in same tree, never early return
  const hasOverlay = viewMode !== "chat";

  // Main chat view: use Static for all completed messages
  // Native terminal scrollback handles scrolling
  // Reset welcome after /clear (clearCount changes → show welcome again)
  React.useEffect(() => {
    if (clearCount > 0) setWelcomeShown(false);
  }, [clearCount]);

  type StaticItem = Message | { id: "__welcome__"; isWelcome: true };
  const showWelcome = serverConfig && !welcomeShown;
  const welcomeItem: StaticItem | null = showWelcome ? { id: "__welcome__", isWelcome: true } : null;
  const staticItems: StaticItem[] = welcomeItem ? [welcomeItem, ...messages] : messages;

  React.useEffect(() => {
    if (serverConfig && !welcomeShown) setWelcomeShown(true);
  }, [serverConfig, welcomeShown]);
  
  return (
    <ErrorBoundary>
    <Box flexDirection="column">
      {/* Static items - rendered once and frozen. Key on clearCount to force remount on /clear */}
      <Box key={`static-${clearCount}`} flexDirection="column">
        <Static items={staticItems}>
          {(item: StaticItem, index: number) => {
            if ("isWelcome" in item) {
              return (
                <Box key="welcome">
                  <Welcome />
                </Box>
              );
            }
            // Spacing: 1 newline between all messages, except consecutive tools (0)
            const prevItem = staticItems[index - 1];
            const isToolMessage = item.role === "tool" || item.role === "tool_chain";
            const prevIsToolMessage = prevItem && !("isWelcome" in prevItem) &&
              (prevItem.role === "tool" || prevItem.role === "tool_chain");
            const needsMargin = index > 0 && !(isToolMessage && prevIsToolMessage);

            return (
              <Box key={item.id} marginTop={needsMargin ? 1 : 0}>
                <MessageDisplay
                  msg={item}
                  renderMarkdown={settings.ui.renderMarkdown}
                />
              </Box>
            );
          }}
        </Static>
      </Box>

      {/* Live content - tool calls, status */}
      {toolChain.length > 0 && (
        <Box marginTop={messages[messages.length - 1]?.role === "user" ? 1 : 0}>
          <ToolChainDisplay items={toolChain} />
        </Box>
      )}

      {/* Thinking indicator — margin when content exists above */}
      {status && (
        <Box marginTop={messages.length > 0 || toolChain.length > 0 ? 1 : 0}>
          <ThinkingIndicator status={status} />
        </Box>
      )}

      {/* Approval dialog - takes priority over choice */}
      {pendingApproval && (
        <ApprovalDialog
          approval={pendingApproval}
          onResult={handleApproval}
        />
      )}

      {/* Choice selector - waits if approval is pending */}
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

      {/* Connection status */}
      {!serverConnected && (
        <Box marginBottom={1}>
          <Text color={colors.status.error}>{BULLET} Server not connected. Run: ntrp serve</Text>
        </Box>
      )}


      {/* Input - always visible, can type during streaming (messages get queued) */}
      <Box marginTop={1}>
      <InputArea
        onSubmit={handleSubmit}
        disabled={!serverConnected || hasOverlay || showSettings || !!pendingApproval || !!pendingChoice}
        focus={isInChatMode && !hasOverlay && !showSettings && !pendingApproval && !pendingChoice}
        commands={COMMANDS}
        queueCount={messageQueue.length}
        skipApprovals={skipApprovals}
        chatModel={serverConfig?.chat_model}
        indexStatus={indexStatus}
      />
      </Box>

      {/* Overlays - rendered below input */}
      {viewMode === "memory" && (
        <MemoryViewer config={config} onClose={closeView} />
      )}
      {viewMode === "schedules" && (
        <SchedulesViewer config={config} onClose={closeView} />
      )}
      {showSettings && (
        <SettingsDialog
          config={config}
          serverConfig={serverConfig}
          settings={settings}
          onUpdate={updateSetting}
          onModelChange={(type: "chat" | "memory", model: string) => updateServerConfig({ [`${type}_model`]: model })}
          onClose={closeSettings}
        />
      )}
    </Box>
    </ErrorBoundary>
  );
}

// Inner component that has access to settings for AccentColorProvider
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

// Wrap with KeypressProvider for custom keyboard handling
export default function App({ config = defaultConfig }: { config?: Config }) {
  return (
    <KeypressProvider>
      <DimensionsProvider>
        <AppWithAccent config={config} />
      </DimensionsProvider>
    </KeypressProvider>
  );
}
