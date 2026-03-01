import { useState, useCallback } from "react";
import { useKeypress, type Key } from "../hooks/useKeypress.js";
import { useTextInput } from "../hooks/useTextInput.js";
import { colors } from "./ui/index.js";
import { TextInputField } from "./ui/input/TextInputField.js";
import { checkHealth } from "../api/client.js";
import { setApiKey } from "../api/fetch.js";
import { setCredentials } from "../lib/secrets.js";
import type { Config } from "../types.js";
import { BULLET } from "../lib/constants.js";

type Field = "serverUrl" | "apiKey";

interface SetupProps {
  initialServerUrl: string;
  onConnect: (config: Config) => void;
}

export function Setup({ initialServerUrl, onConnect }: SetupProps) {
  const [activeField, setActiveField] = useState<Field>("serverUrl");
  const [serverUrl, setServerUrl] = useState(initialServerUrl);
  const [serverUrlCursor, setServerUrlCursor] = useState(initialServerUrl.length);
  const [apiKey, setApiKeyValue] = useState("");
  const [apiKeyCursor, setApiKeyCursor] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  const serverUrlInput = useTextInput({
    text: serverUrl,
    cursorPos: serverUrlCursor,
    setText: setServerUrl,
    setCursorPos: setServerUrlCursor,
  });

  const apiKeyInput = useTextInput({
    text: apiKey,
    cursorPos: apiKeyCursor,
    setText: setApiKeyValue,
    setCursorPos: setApiKeyCursor,
  });

  const connect = useCallback(async () => {
    const url = serverUrl.trim();
    const key = apiKey.trim();

    if (!url) {
      setError("Server URL is required");
      return;
    }
    if (!key) {
      setError("API key is required");
      return;
    }

    setError(null);
    setConnecting(true);

    try {
      setApiKey(key);
      const config: Config = { serverUrl: url, apiKey: key, needsSetup: false };
      const health = await checkHealth(config);

      if (!health.ok) {
        setError("Could not connect to server");
        setConnecting(false);
        return;
      }

      await setCredentials(url, key);
      onConnect(config);
    } catch {
      setError("Could not connect to server");
      setConnecting(false);
    }
  }, [serverUrl, apiKey, onConnect]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (connecting) return;

      if (key.name === "tab" || (key.name === "down" && activeField === "serverUrl") || (key.name === "up" && activeField === "apiKey")) {
        setActiveField((f) => (f === "serverUrl" ? "apiKey" : "serverUrl"));
        return;
      }

      if (key.name === "return") {
        connect();
        return;
      }

      if (activeField === "serverUrl") {
        serverUrlInput.handleKey(key);
      } else {
        apiKeyInput.handleKey(key);
      }
    },
    [activeField, connecting, connect, serverUrlInput, apiKeyInput]
  );

  useKeypress(handleKeypress, { isActive: true });

  const maskedKey = apiKey ? "\u2022".repeat(Math.min(apiKey.length, 40)) : "";

  return (
    <box flexDirection="column" paddingTop={2} paddingLeft={4}>
      <text><span fg={colors.text.primary}><strong>ntrp</strong></span><span fg={colors.text.muted}> — setup</span></text>

      <box flexDirection="column" marginTop={2} gap={1}>
        <box flexDirection="row">
          <box width={14} flexShrink={0}>
            <text><span fg={activeField === "serverUrl" ? colors.text.primary : colors.text.secondary}>Server URL</span></text>
          </box>
          <text><span fg={colors.text.muted}> </span></text>
          {activeField === "serverUrl" ? (
            <TextInputField value={serverUrl} cursorPos={serverUrlCursor} placeholder="http://localhost:8000" />
          ) : (
            <text><span fg={colors.text.secondary}>{serverUrl || "http://localhost:8000"}</span></text>
          )}
        </box>

        <box flexDirection="row">
          <box width={14} flexShrink={0}>
            <text><span fg={activeField === "apiKey" ? colors.text.primary : colors.text.secondary}>API Key</span></text>
          </box>
          <text><span fg={colors.text.muted}> </span></text>
          {activeField === "apiKey" ? (
            <TextInputField value={apiKey} cursorPos={apiKeyCursor} placeholder="your-api-key" />
          ) : (
            <text><span fg={colors.text.secondary}>{maskedKey || "your-api-key"}</span></text>
          )}
        </box>
      </box>

      <box marginTop={2}>
        {connecting ? (
          <text><span fg={colors.text.muted}>Connecting...</span></text>
        ) : (
          <text><span fg={colors.text.muted}>press </span><span fg={colors.text.primary}>enter</span><span fg={colors.text.muted}> to connect  </span><span fg={colors.text.disabled}>tab to switch fields</span></text>
        )}
      </box>

      {error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{BULLET} {error}</span></text>
        </box>
      )}
    </box>
  );
}
