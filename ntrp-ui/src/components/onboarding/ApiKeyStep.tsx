import React from "react";
import { Dialog, colors, Hints } from "../ui/index.js";

export interface ApiKeyStepProps {
  providerName: string;
  apiKeyValue: string;
  apiKeyCursor: number;
  saving: boolean;
  error: string | null;
  onBack: () => void;
}

export function ApiKeyStep({ providerName, apiKeyValue, apiKeyCursor, saving, error, onBack }: ApiKeyStepProps) {
  const maskedKey = apiKeyValue ? "\u2022".repeat(Math.min(apiKeyValue.length, 40)) : "";
  const footer = saving
    ? <text><span fg={colors.text.muted}>Connecting...</span></text>
    : <Hints items={[["enter", "connect"], ["esc", "back"]]} />;

  return (
    <Dialog title={`${providerName.toUpperCase()} API KEY`} size="medium" onClose={onBack} closable footer={footer}>
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
}
