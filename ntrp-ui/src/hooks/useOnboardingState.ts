import { useState, useCallback, useEffect, useRef } from "react";
import { useTextInput } from "./useTextInput.js";
import type { Key } from "./useKeypress.js";
import { CUSTOM_PRESETS, CUSTOM_FIELDS, type CustomField } from "../components/onboarding/index.js";
import { getProviders, connectProvider, connectProviderOAuth, updateConfig, addCustomModel, type ProviderInfo } from "../api/client.js";
import type { Config } from "../types.js";

type Step = "providers" | "apiKey" | "modelSelect" | "customModel";

export function getStringModels(provider: ProviderInfo | null | undefined): string[] {
  if (!provider?.models || !Array.isArray(provider.models)) return [];
  return provider.models.filter((m): m is string => typeof m === "string");
}

interface UseOnboardingStateOptions {
  config: Config;
  closable: boolean;
  onClose: () => void;
  onDone: () => void;
}

export function useOnboardingState({ config, closable, onClose, onDone }: UseOnboardingStateOptions) {
  const [step, setStep] = useState<Step>("providers");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
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
  const providersRef = useRef(providers);
  providersRef.current = providers;

  const refreshProviders = useCallback(async () => {
    try {
      const result = await getProviders(config);
      setProviders(result.providers);
      return result.providers;
    } catch {
      return providersRef.current;
    }
  }, [config]);

  useEffect(() => { refreshProviders(); }, [refreshProviders]);

  const showModels = useCallback((provider: ProviderInfo | null | undefined) => {
    setModelList(getStringModels(provider));
    setStep("modelSelect");
  }, []);

  const goBack = useCallback(() => setStep("providers"), []);

  const handleSelectProvider = useCallback(async (providerId: string) => {
    const provider = providers.find(p => p.id === providerId);
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

    setSelectedProvider(provider);
    setError(null);

    if (provider.id === "claude_oauth") {
      if (provider.connected) {
        showModels(provider);
      } else {
        setSaving(true);
        try {
          await connectProviderOAuth(config, "anthropic");
          const fresh = await refreshProviders();
          const updated = fresh.find(p => p.id === "claude_oauth");
          if (!updated) {
            setError("OAuth connected but provider not found \u2014 try again");
            return;
          }
          setSelectedProvider(updated);
          showModels(updated);
        } catch (e) {
          setError(e instanceof Error ? e.message : "OAuth failed");
        } finally {
          setSaving(false);
        }
      }
    } else if (provider.connected) {
      showModels(provider);
    } else {
      setApiKeyValue("");
      setApiKeyCursor(0);
      setStep("apiKey");
    }
  }, [providers, config, refreshProviders, showModels]);

  const handleSubmitApiKey = useCallback(async () => {
    const key = apiKeyValue.trim();
    if (!key || !selectedProvider) return;

    setSaving(true);
    setError(null);
    try {
      await connectProvider(config, selectedProvider.id, key);
      await refreshProviders();
      if (hasConnected) {
        setStep("providers");
      } else {
        showModels(selectedProvider);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setSaving(false);
    }
  }, [apiKeyValue, selectedProvider, hasConnected, config, refreshProviders, showModels]);

  const handleSelectModel = useCallback(async (model: string) => {
    const id = selectedProvider?.id === "claude_oauth" ? `oauth:${model}` : model;
    setSaving(true);
    setError(null);
    try {
      await updateConfig(config, { chat_model: id });
      await refreshProviders();
      if (!closable) {
        onDone();
      } else {
        setStep("providers");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to set model");
    } finally {
      setSaving(false);
    }
  }, [config, selectedProvider, refreshProviders, closable, onDone]);

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

      if (step === "apiKey") {
        if (key.name === "escape") { setStep("providers"); return; }
        if (key.name === "return") { handleSubmitApiKey(); return; }
        apiKeyInput.handleKey(key);
        return;
      }

      if (step === "customModel") {
        if (key.name === "escape") { setStep("providers"); return; }

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
          if (key.name === "return" || key.name === "tab") { setCustomField("baseUrl"); return; }
          return;
        }

        if (key.name === "tab" || key.name === "return") {
          const idx = CUSTOM_FIELDS.indexOf(customField);
          if (customField === "contextWindow" && key.name === "return") { handleSubmitCustomModel(); return; }
          if (idx < CUSTOM_FIELDS.length - 1) setCustomField(CUSTOM_FIELDS[idx + 1]);
          return;
        }

        if (key.shift && key.name === "tab") {
          const idx = CUSTOM_FIELDS.indexOf(customField);
          if (idx > 0) setCustomField(CUSTOM_FIELDS[idx - 1]);
          return;
        }

        if (customField === "baseUrl") baseUrlInput.handleKey(key);
        else if (customField === "modelId") modelIdInput.handleKey(key);
        else if (customField === "apiKey") customApiKeyInput.handleKey(key);
        else if (customField === "contextWindow") contextWindowInput.handleKey(key);
      }
    },
    [
      step, saving,
      handleSubmitApiKey, handleSubmitCustomModel,
      apiKeyInput, customField, presetIndex,
      baseUrlInput, modelIdInput, customApiKeyInput, contextWindowInput,
    ]
  );

  return {
    step,
    providers,
    selectedProvider,
    error,
    saving,
    hasConnected,

    apiKeyValue,
    apiKeyCursor,

    modelList,

    customField,
    presetIndex,
    baseUrl,
    baseUrlCursor,
    modelId,
    modelIdCursor,
    customApiKey,
    customApiKeyCursor,
    contextWindow,
    contextWindowCursor,

    handleSelectProvider,
    handleSubmitApiKey,
    handleSelectModel,
    handleSubmitCustomModel,
    handleKeypress,
    goBack,
  };
}
