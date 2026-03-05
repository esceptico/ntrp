import { useCallback } from "react";
import { useRenderer } from "@opentui/react";
import { useKeypress, type Key } from "../hooks/useKeypress.js";
import { useOnboardingState } from "../hooks/useOnboardingState.js";
import { ProviderList, ApiKeyStep, ModelSelect, CustomModelForm } from "./onboarding/index.js";
import type { Config } from "../types.js";

interface ProviderOnboardingProps {
  config: Config;
  closable?: boolean;
  onClose: () => void;
  onDone: () => void;
}

export function ProviderOnboarding({ config, closable = false, onClose, onDone }: ProviderOnboardingProps) {
  const renderer = useRenderer();
  const state = useOnboardingState({ config, closable, onClose, onDone });

  const handleCtrlC = useCallback((key: Key) => {
    if (key.ctrl && key.name === "c") renderer.destroy();
  }, [renderer]);

  useKeypress(handleCtrlC, { isActive: true });
  useKeypress(state.handleKeypress, { isActive: state.step === "apiKey" || state.step === "customModel" });

  if (state.step === "providers") {
    return (
      <ProviderList
        providers={state.providers}
        hasConnected={state.hasConnected}
        closable={closable}
        saving={state.saving}
        isActive={state.step === "providers"}
        onSelect={state.handleSelectProvider}
        onClose={onClose}
        onDone={onDone}
      />
    );
  }

  if (state.step === "apiKey") {
    return (
      <ApiKeyStep
        providerName={state.selectedProvider?.name ?? ""}
        apiKeyValue={state.apiKeyValue}
        apiKeyCursor={state.apiKeyCursor}
        saving={state.saving}
        error={state.error}
        onBack={state.goBack}
      />
    );
  }

  if (state.step === "modelSelect") {
    return (
      <ModelSelect
        modelList={state.modelList}
        saving={state.saving}
        isActive={state.step === "modelSelect"}
        error={state.error}
        onSelect={state.handleSelectModel}
        onBack={state.goBack}
      />
    );
  }

  if (state.step === "customModel") {
    return (
      <CustomModelForm
        customField={state.customField}
        presetIndex={state.presetIndex}
        baseUrl={state.baseUrl}
        baseUrlCursor={state.baseUrlCursor}
        modelId={state.modelId}
        modelIdCursor={state.modelIdCursor}
        customApiKey={state.customApiKey}
        customApiKeyCursor={state.customApiKeyCursor}
        contextWindow={state.contextWindow}
        contextWindowCursor={state.contextWindowCursor}
        saving={state.saving}
        error={state.error}
        onBack={state.goBack}
      />
    );
  }

  return null;
}
