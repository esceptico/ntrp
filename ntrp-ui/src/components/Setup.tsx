import { useState, useCallback } from "react";
import { useKeypress, type Key } from "../hooks/useKeypress.js";
import { useTextInput } from "../hooks/useTextInput.js";
import { Dialog, colors, Hints } from "./ui/index.js";
import { TextInputField } from "./ui/input/TextInputField.js";
import { checkHealth } from "../api/client.js";
import { setApiKey } from "../api/fetch.js";
import { setCredentials } from "../lib/secrets.js";
import type { Config } from "../types.js";

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
      onConnect({ ...config, needsProvider: !health.hasProviders });
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

  const items = [
    { field: "serverUrl" as Field, label: "Server URL", value: serverUrl, cursor: serverUrlCursor, placeholder: "http://localhost:8000" },
    { field: "apiKey" as Field, label: "API Key", value: apiKey, displayValue: maskedKey, cursor: apiKeyCursor, placeholder: "your-api-key" },
  ];

  const footer = connecting
    ? <text><span fg={colors.text.muted}>Connecting...</span></text>
    : <Hints items={[["enter", "connect"], ["tab/↑↓", "switch"]]} />;

  return (
    <Dialog title="CONNECT" size="medium" onClose={() => {}} closable={false} footer={footer}>
      {() => (
        <box flexDirection="column">
          {items.map((item) => {
            const selected = item.field === activeField;
            const isEditing = selected;

            return (
              <box key={item.label} flexDirection="row">
                <text>
                  <span fg={selected ? colors.text.primary : colors.text.disabled}>{selected ? "▸ " : "  "}</span>
                  <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.label.padEnd(14)}</span>
                </text>
                {isEditing ? (
                  <TextInputField
                    value={item.value}
                    cursorPos={item.cursor}
                    placeholder={item.placeholder}
                  />
                ) : (
                  <text>
                    <span fg={colors.text.muted}>{item.displayValue ?? (item.value || item.placeholder)}</span>
                  </text>
                )}
              </box>
            );
          })}

          {error && (
            <box marginTop={1}>
              <text><span fg={colors.status.error}>  {error}</span></text>
            </box>
          )}
        </box>
      )}
    </Dialog>
  );
}
