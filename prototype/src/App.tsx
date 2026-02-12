import { useState, useCallback, useEffect, useMemo } from "react";
import { useRenderer } from "@opentui/react";
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
  Welcome,
  ApprovalDialog,
  ErrorBoundary,
} from "./components/index.js";
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
    refreshIndexStatus,
    updateSessionInfo,
    toggleSkipApprovals,
    updateServerConfig,
  } = session;

  const [viewMode, setViewMode] = useState<ViewMode>("chat");
  const [messageQueue, setMessageQueue] = useState<string[]>([]);
  const [welcomeShown, setWelcomeShown] = useState(false);

  const [skills, setSkills] = useState<Skill[]>([]);
  useEffect(() => {
    getSkills(config).then(r => setSkills(r.skills)).catch(() => {});
  }, [config]);

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
    addMessage,
    clearMessages,
    sendMessage,
    handleChoice,
    cancelChoice,
    handleApproval,
    cancel,
  } = streaming;

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

  // Show welcome on first load
  const showWelcome = serverConfig && !welcomeShown;
  useEffect(() => {
    if (serverConfig && !welcomeShown) setWelcomeShown(true);
  }, [serverConfig, welcomeShown]);

  return (
    <ErrorBoundary>
    <box flexDirection="column" width={width} height={height} paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1} gap={1} backgroundColor={colors.background.base}>
      {/* Scrollable message area */}
      <scrollbox flexGrow={1} stickyScroll={true} stickyStart="bottom" style={{ scrollbarOptions: { visible: false } }}>
        {showWelcome && <Welcome />}

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

      {/* Connection status — pinned above input */}
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
        />
      </box>

      {/* Overlays — absolute positioned to cover full screen */}
      {viewMode === "memory" && (
        <box position="absolute" top={0} left={0} width={width} height={height}>
          <MemoryViewer config={config} onClose={closeView} />
        </box>
      )}
      {viewMode === "schedules" && (
        <box position="absolute" top={0} left={0} width={width} height={height}>
          <SchedulesViewer config={config} onClose={closeView} />
        </box>
      )}
      {viewMode === "dashboard" && (
        <box position="absolute" top={0} left={0} width={width} height={height}>
          <DashboardViewer config={config} onClose={closeView} />
        </box>
      )}
      {showSettings && (
        <box position="absolute" top={0} left={0} width={width} height={height}>
          <SettingsDialog
            config={config}
            serverConfig={serverConfig}
            settings={settings}
            onUpdate={updateSetting}
            onModelChange={(type: "chat" | "memory", model: string) => updateServerConfig({ [`${type}_model`]: model })}
            onServerConfigChange={(newConfig) => updateServerConfig(newConfig)}
            onClose={closeSettings}
          />
        </box>
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
