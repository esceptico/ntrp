import { useState, useCallback } from "react";
import { useRenderer } from "@opentui/react";
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

function windowText(value: string, cursorPos: number, maxWidth: number): { text: string; cursor: number } {
  if (value.length <= maxWidth) return { text: value, cursor: cursorPos };
  let start = Math.max(0, cursorPos - Math.floor(maxWidth / 2));
  if (start + maxWidth > value.length) start = Math.max(0, value.length - maxWidth);
  return { text: value.slice(start, start + maxWidth), cursor: cursorPos - start };
}

export function Setup({ initialServerUrl, onConnect }: SetupProps) {
  const renderer = useRenderer();
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
      if (key.ctrl && key.name === "c") {
        renderer.destroy();
        return;
      }

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

  const LABEL_WIDTH = 16;

  const footer = connecting
    ? <text><span fg={colors.text.muted}>Connecting...</span></text>
    : <Hints items={[["enter", "connect"], ["tab/↑↓", "switch"], ["^c", "exit"]]} />;

  return (
    <Dialog title="CONNECT" size="medium" onClose={() => {}} closable={false} footer={footer}>
      {({ width }) => {
        const inputMaxWidth = Math.max(8, width - LABEL_WIDTH);

        const maskedApiKey = "\u2022".repeat(apiKey.length);
        const serverUrlWin = windowText(serverUrl, serverUrlCursor, inputMaxWidth);
        const apiKeyWin = windowText(maskedApiKey, apiKeyCursor, inputMaxWidth);

        const items = [
          { field: "serverUrl" as Field, label: "Server URL", display: serverUrlWin.text, cursor: serverUrlWin.cursor, displayInactive: serverUrl, placeholder: "http://localhost:6877" },
          { field: "apiKey" as Field, label: "API Key", display: apiKeyWin.text, cursor: apiKeyWin.cursor, displayInactive: maskedApiKey || null, placeholder: "your-api-key" },
        ];

        return (
          <box flexDirection="column">
            {items.map((item) => {
              const selected = item.field === activeField;

              return (
                <box key={item.label} flexDirection="row">
                  <box width={LABEL_WIDTH} flexShrink={0}>
                    <text>
                      <span fg={selected ? colors.text.primary : colors.text.disabled}>{selected ? "> " : "  "}</span>
                      <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.label.padEnd(14)}</span>
                    </text>
                  </box>
                  {selected ? (
                    <TextInputField
                      value={item.display}
                      cursorPos={item.cursor}
                      placeholder={item.placeholder}
                    />
                  ) : (
                    <text>
                      <span fg={colors.text.muted}>{item.displayInactive || item.placeholder}</span>
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
        );
      }}
    </Dialog>
  );
}
