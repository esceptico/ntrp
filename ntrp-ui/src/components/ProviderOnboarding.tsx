import { useState, useCallback, useEffect } from "react";
import { useKeypress, type Key } from "../hooks/useKeypress.js";
import { useTextInput } from "../hooks/useTextInput.js";
import { Dialog, BaseSelectionList, colors, Hints, type RenderItemContext } from "./ui/index.js";
import { TextInputField } from "./ui/input/TextInputField.js";
import { getProviders, connectProvider, addCustomModel, type ProviderInfo } from "../api/client.js";
import type { Config } from "../types.js";

type Step = "providers" | "apiKey" | "modelSelect" | "customModel";

interface CustomPreset {
  name: string;
  base_url: string;
  needs_key: boolean;
}

const CUSTOM_PRESETS: CustomPreset[] = [
  { name: "Ollama", base_url: "http://localhost:11434/v1", needs_key: false },
  { name: "vLLM", base_url: "http://localhost:8000/v1", needs_key: false },
  { name: "OpenRouter", base_url: "https://openrouter.ai/api/v1", needs_key: true },
  { name: "LM Studio", base_url: "http://localhost:1234/v1", needs_key: false },
  { name: "Together", base_url: "https://api.together.xyz/v1", needs_key: true },
  { name: "Other", base_url: "", needs_key: false },
];

type CustomField = "preset" | "baseUrl" | "modelId" | "apiKey" | "contextWindow";
const CUSTOM_FIELDS: CustomField[] = ["preset", "baseUrl", "modelId", "apiKey", "contextWindow"];

interface ProviderOnboardingProps {
  config: Config;
  closable?: boolean;
  onClose: () => void;
  onDone: () => void;
}

export function ProviderOnboarding({ config, closable = false, onClose, onDone }: ProviderOnboardingProps) {
  const [step, setStep] = useState<Step>("providers");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedProvider, setSelectedProvider] = useState<ProviderInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // API key input
  const [apiKeyValue, setApiKeyValue] = useState("");
  const [apiKeyCursor, setApiKeyCursor] = useState(0);
  const apiKeyInput = useTextInput({
    text: apiKeyValue,
    cursorPos: apiKeyCursor,
    setText: setApiKeyValue,
    setCursorPos: setApiKeyCursor,
  });

  // Model selection
  const [modelIndex, setModelIndex] = useState(0);
  const [modelList, setModelList] = useState<string[]>([]);

  // Custom model form
  const [customField, setCustomField] = useState<CustomField>("preset");
  const [presetIndex, setPresetIndex] = useState(0);
  const [baseUrl, setBaseUrl] = useState("");
  const [baseUrlCursor, setBaseUrlCursor] = useState(0);
  const [modelId, setModelId] = useState("");
  const [modelIdCursor, setModelIdCursor] = useState(0);
  const [customApiKey, setCustomApiKey] = useState("");
  const [customApiKeyCursor, setCustomApiKeyCursor] = useState(0);
  const [contextWindow, setContextWindow] = useState("128000");
  const [contextWindowCursor, setContextWindowCursor] = useState(6);

  const baseUrlInput = useTextInput({ text: baseUrl, cursorPos: baseUrlCursor, setText: setBaseUrl, setCursorPos: setBaseUrlCursor });
  const modelIdInput = useTextInput({ text: modelId, cursorPos: modelIdCursor, setText: setModelId, setCursorPos: setModelIdCursor });
  const customApiKeyInput = useTextInput({ text: customApiKey, cursorPos: customApiKeyCursor, setText: setCustomApiKey, setCursorPos: setCustomApiKeyCursor });
  const contextWindowInput = useTextInput({ text: contextWindow, cursorPos: contextWindowCursor, setText: setContextWindow, setCursorPos: setContextWindowCursor });

  const hasConnected = providers.some(p => p.connected);

  const refreshProviders = useCallback(async () => {
    try {
      const result = await getProviders(config);
      setProviders(result.providers);
    } catch {}
  }, [config]);

  useEffect(() => { refreshProviders(); }, [refreshProviders]);

  const handleSelectProvider = useCallback(() => {
    const provider = providers[selectedIndex];
    if (!provider) return;

    if (provider.id === "custom") {
      setStep("customModel");
      setCustomField("preset");
      setPresetIndex(0);
      const preset = CUSTOM_PRESETS[0];
      setBaseUrl(preset.base_url);
      setBaseUrlCursor(preset.base_url.length);
      setCustomApiKey("");
      setCustomApiKeyCursor(0);
      setModelId("");
      setModelIdCursor(0);
      setContextWindow("128000");
      setContextWindowCursor(6);
      setError(null);
      return;
    }

    if (provider.connected && !provider.from_env) {
      return;
    }

    setSelectedProvider(provider);
    setApiKeyValue("");
    setApiKeyCursor(0);
    setError(null);
    setStep("apiKey");
  }, [providers, selectedIndex]);

  const handleSubmitApiKey = useCallback(async () => {
    const key = apiKeyValue.trim();
    if (!key || !selectedProvider) return;

    setSaving(true);
    setError(null);
    try {
      await connectProvider(config, selectedProvider.id, key);
      await refreshProviders();

      // Move to model selection
      const models = Array.isArray(selectedProvider.models) ? selectedProvider.models.filter((m): m is string => typeof m === "string") : [];
      if (models.length > 0) {
        setModelList(models);
        setModelIndex(0);
        setStep("modelSelect");
      } else {
        setStep("providers");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setSaving(false);
    }
  }, [apiKeyValue, selectedProvider, config, refreshProviders]);

  const handleSelectModel = useCallback(async () => {
    const model = modelList[modelIndex];
    if (!model || !selectedProvider) return;

    setSaving(true);
    setError(null);
    try {
      await connectProvider(config, selectedProvider.id, apiKeyValue.trim(), model);
      await refreshProviders();
      setStep("providers");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to set model");
    } finally {
      setSaving(false);
    }
  }, [modelList, modelIndex, selectedProvider, config, apiKeyValue, refreshProviders]);

  const handleSubmitCustomModel = useCallback(async () => {
    const id = modelId.trim();
    const url = baseUrl.trim();
    const ctxStr = contextWindow.trim();
    if (!id || !url) {
      setError("Model ID and Base URL are required");
      return;
    }
    const ctx = parseInt(ctxStr, 10);
    if (isNaN(ctx) || ctx <= 0) {
      setError("Context window must be a positive number");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await addCustomModel(config, {
        model_id: id,
        base_url: url,
        context_window: ctx,
        api_key: customApiKey.trim() || undefined,
      });
      await refreshProviders();
      setStep("providers");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add model");
    } finally {
      setSaving(false);
    }
  }, [modelId, baseUrl, contextWindow, customApiKey, config, refreshProviders]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (saving) return;

      if (step === "providers") {
        if (key.name === "escape") {
          if (hasConnected || closable) {
            if (hasConnected) onDone();
            else onClose();
          }
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setSelectedIndex(i => Math.max(0, i - 1));
          return;
        }
        if (key.name === "down" || key.name === "j") {
          setSelectedIndex(i => Math.min(providers.length - 1, i + 1));
          return;
        }
        if (key.name === "return") {
          handleSelectProvider();
          return;
        }
      }

      if (step === "apiKey") {
        if (key.name === "escape") {
          setStep("providers");
          return;
        }
        if (key.name === "return") {
          handleSubmitApiKey();
          return;
        }
        apiKeyInput.handleKey(key);
        return;
      }

      if (step === "modelSelect") {
        if (key.name === "escape") {
          // Skip model selection, go back
          setStep("providers");
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setModelIndex(i => Math.max(0, i - 1));
          return;
        }
        if (key.name === "down" || key.name === "j") {
          setModelIndex(i => Math.min(modelList.length - 1, i + 1));
          return;
        }
        if (key.name === "return") {
          handleSelectModel();
          return;
        }
      }

      if (step === "customModel") {
        if (key.name === "escape") {
          setStep("providers");
          return;
        }

        if (customField === "preset") {
          if (key.name === "left" || key.name === "h") {
            setPresetIndex(i => {
              const next = Math.max(0, i - 1);
              const p = CUSTOM_PRESETS[next];
              setBaseUrl(p.base_url);
              setBaseUrlCursor(p.base_url.length);
              return next;
            });
            return;
          }
          if (key.name === "right" || key.name === "l") {
            setPresetIndex(i => {
              const next = Math.min(CUSTOM_PRESETS.length - 1, i + 1);
              const p = CUSTOM_PRESETS[next];
              setBaseUrl(p.base_url);
              setBaseUrlCursor(p.base_url.length);
              return next;
            });
            return;
          }
          if (key.name === "return" || key.name === "tab") {
            setCustomField("baseUrl");
            return;
          }
          return;
        }

        // Tab/return advance to next field
        if (key.name === "tab" || key.name === "return") {
          const idx = CUSTOM_FIELDS.indexOf(customField);
          if (customField === "contextWindow" && key.name === "return") {
            handleSubmitCustomModel();
            return;
          }
          if (idx < CUSTOM_FIELDS.length - 1) {
            setCustomField(CUSTOM_FIELDS[idx + 1]);
          }
          return;
        }

        // Shift+tab goes back
        if (key.shift && key.name === "tab") {
          const idx = CUSTOM_FIELDS.indexOf(customField);
          if (idx > 0) {
            setCustomField(CUSTOM_FIELDS[idx - 1]);
          }
          return;
        }

        // Route to the right text input
        if (customField === "baseUrl") baseUrlInput.handleKey(key);
        else if (customField === "modelId") modelIdInput.handleKey(key);
        else if (customField === "apiKey") customApiKeyInput.handleKey(key);
        else if (customField === "contextWindow") contextWindowInput.handleKey(key);
      }
    },
    [
      step, saving, providers, selectedIndex, hasConnected, closable,
      handleSelectProvider, handleSubmitApiKey, handleSelectModel, handleSubmitCustomModel,
      apiKeyInput, modelList, modelIndex, customField, presetIndex,
      baseUrlInput, modelIdInput, customApiKeyInput, contextWindowInput,
      onClose, onDone,
    ]
  );

  useKeypress(handleKeypress, { isActive: true });

  const renderProviderList = () => {
    const subtitle = hasConnected
      ? "Add another provider or press esc to start"
      : "Connect an LLM provider to get started";

    const footer = hasConnected
      ? <Hints items={[["enter", "select"], ["\u2191\u2193", "navigate"], ["esc", "done"]]} />
      : <Hints items={[["enter", "select"], ["\u2191\u2193", "navigate"]]} />;

    return (
      <Dialog title="PROVIDERS" size="medium" onClose={onClose} closable={closable} footer={footer}>
        {() => (
          <box flexDirection="column">
            <box marginBottom={1}>
              <text><span fg={colors.text.muted}>{subtitle}</span></text>
            </box>
            <BaseSelectionList
              items={providers}
              selectedIndex={selectedIndex}
              visibleLines={8}
              getKey={(p) => p.id}
              renderItem={(provider: ProviderInfo, ctx: RenderItemContext) => {
                if (provider.id === "custom") {
                  const count = provider.model_count ?? 0;
                  return (
                    <text>
                      <span fg={ctx.colors.text}>{provider.name}</span>
                      {count > 0 && <span fg={colors.text.muted}>{` (${count} model${count !== 1 ? "s" : ""})`}</span>}
                    </text>
                  );
                }

                const connected = provider.connected;
                const fromEnv = provider.from_env;

                return (
                  <text>
                    <span fg={ctx.colors.text}>{provider.name}</span>
                    {connected && <span fg={colors.status.success}>{" \u2713"}</span>}
                    {connected && provider.key_hint && <span fg={colors.text.disabled}>{` ${provider.key_hint}`}</span>}
                    {fromEnv && <span fg={colors.text.muted}>{" (env)"}</span>}
                  </text>
                );
              }}
            />
          </box>
        )}
      </Dialog>
    );
  };

  const renderApiKeyStep = () => {
    if (!selectedProvider) return null;

    const maskedKey = apiKeyValue ? "\u2022".repeat(Math.min(apiKeyValue.length, 40)) : "";
    const footer = saving
      ? <text><span fg={colors.text.muted}>Connecting...</span></text>
      : <Hints items={[["enter", "connect"], ["esc", "back"]]} />;

    return (
      <Dialog title={`${selectedProvider.name.toUpperCase()} API KEY`} size="medium" onClose={() => setStep("providers")} closable footer={footer}>
        {() => (
          <box flexDirection="column">
            <box flexDirection="row">
              <text><span fg={colors.text.primary}>{"\u25B8 API Key".padEnd(16)}</span></text>
              {apiKeyValue ? (
                <text>
                  <span fg={colors.text.primary}>{maskedKey.slice(0, apiKeyCursor)}</span>
                  <span bg={colors.text.primary} fg={colors.contrast}>{maskedKey[apiKeyCursor] || " "}</span>
                  <span fg={colors.text.primary}>{maskedKey.slice(apiKeyCursor + 1)}</span>
                </text>
              ) : (
                <text>
                  <span fg={colors.text.muted}>sk-...</span>
                  <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>
                </text>
              )}
            </box>
            {error && (
              <box marginTop={1}>
                <text><span fg={colors.status.error}>  {error}</span></text>
              </box>
            )}
          </box>
        )}
      </Dialog>
    );
  };

  const renderModelSelect = () => {
    const footer = saving
      ? <text><span fg={colors.text.muted}>Saving...</span></text>
      : <Hints items={[["enter", "select"], ["\u2191\u2193", "navigate"], ["esc", "skip"]]} />;

    return (
      <Dialog title="DEFAULT CHAT MODEL" size="medium" onClose={() => setStep("providers")} closable footer={footer}>
        {() => (
          <box flexDirection="column">
            <BaseSelectionList
              items={modelList}
              selectedIndex={modelIndex}
              visibleLines={8}
              getKey={(m) => m}
              renderItem={(model: string, ctx: RenderItemContext) => (
                <text><span fg={ctx.colors.text}>{model}</span></text>
              )}
            />
            {error && (
              <box marginTop={1}>
                <text><span fg={colors.status.error}>  {error}</span></text>
              </box>
            )}
          </box>
        )}
      </Dialog>
    );
  };

  const renderCustomModelForm = () => {
    const footer = saving
      ? <text><span fg={colors.text.muted}>Adding model...</span></text>
      : customField === "preset"
        ? <Hints items={[["←→", "preset"], ["tab", "next field"], ["esc", "back"]]} />
        : <Hints items={[["tab", "next field"], ["enter", customField === "contextWindow" ? "add model" : "next"], ["esc", "back"]]} />;

    const fieldItems: Array<{ field: CustomField; label: string; value: string; cursor: number; placeholder: string; masked?: boolean }> = [
      { field: "baseUrl", label: "Base URL", value: baseUrl, cursor: baseUrlCursor, placeholder: "http://localhost:11434/v1" },
      { field: "modelId", label: "Model ID", value: modelId, cursor: modelIdCursor, placeholder: "ollama/llama3" },
      { field: "apiKey", label: "API Key", value: customApiKey, cursor: customApiKeyCursor, placeholder: "(optional for local)", masked: true },
      { field: "contextWindow", label: "Context", value: contextWindow, cursor: contextWindowCursor, placeholder: "128000" },
    ];

    return (
      <Dialog title="ADD CUSTOM MODEL" size="medium" onClose={() => setStep("providers")} closable footer={footer}>
        {() => (
          <box flexDirection="column">
            {/* Preset selector */}
            <box marginBottom={1}>
              <text>
                <span fg={customField === "preset" ? colors.text.primary : colors.text.disabled}>{customField === "preset" ? "\u25B8 " : "  "}</span>
                <span fg={customField === "preset" ? colors.text.primary : colors.text.secondary}>{"Preset".padEnd(14)}</span>
              </text>
              <text>
                {CUSTOM_PRESETS.map((p, i) => (
                  <span key={p.name} fg={i === presetIndex ? colors.selection.active : colors.text.muted}>
                    {i > 0 ? "  " : ""}{i === presetIndex ? `[${p.name}]` : p.name}
                  </span>
                ))}
              </text>
            </box>

            {/* Text fields */}
            {fieldItems.map((item) => {
              const isActive = item.field === customField;
              const displayValue = item.masked && item.value ? "\u2022".repeat(Math.min(item.value.length, 40)) : item.value;
              return (
                <box key={item.field} flexDirection="row">
                  <text>
                    <span fg={isActive ? colors.text.primary : colors.text.disabled}>{isActive ? "\u25B8 " : "  "}</span>
                    <span fg={isActive ? colors.text.primary : colors.text.secondary}>{item.label.padEnd(14)}</span>
                  </text>
                  {isActive ? (
                    item.masked ? (
                      (() => {
                        const masked = item.value ? "\u2022".repeat(Math.min(item.value.length, 40)) : "";
                        return item.value ? (
                          <text>
                            <span fg={colors.text.primary}>{masked.slice(0, item.cursor)}</span>
                            <span bg={colors.text.primary} fg={colors.contrast}>{masked[item.cursor] || " "}</span>
                            <span fg={colors.text.primary}>{masked.slice(item.cursor + 1)}</span>
                          </text>
                        ) : (
                          <text>
                            <span fg={colors.text.muted}>{item.placeholder}</span>
                            <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>
                          </text>
                        );
                      })()
                    ) : (
                      <TextInputField value={item.value} cursorPos={item.cursor} placeholder={item.placeholder} />
                    )
                  ) : (
                    <text><span fg={colors.text.muted}>{displayValue || item.placeholder}</span></text>
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
  };

  if (step === "providers") return renderProviderList();
  if (step === "apiKey") return renderApiKeyStep();
  if (step === "modelSelect") return renderModelSelect();
  if (step === "customModel") return renderCustomModelForm();
  return null;
}
