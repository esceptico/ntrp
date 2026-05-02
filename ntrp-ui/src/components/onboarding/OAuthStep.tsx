import React from "react";
import { Dialog, colors, Hints } from "../ui/index.js";

export interface OAuthStepProps {
  providerName: string;
  url: string | null;
  instructions: string | null;
  saving: boolean;
  error: string | null;
  onBack: () => void;
}

export function OAuthStep({ providerName, url, instructions, saving, error, onBack }: OAuthStepProps) {
  const footer = saving
    ? <text><span fg={colors.text.muted}>Starting sign-in...</span></text>
    : <Hints items={[["esc", "back"]]} />;

  return (
    <Dialog title={`${providerName.toUpperCase()} SIGN-IN`} size="medium" onClose={onBack} closable footer={footer}>
      {() => (
        <box flexDirection="column">
          <text><span fg={colors.text.primary}>OpenAI browser sign-in is running.</span></text>
          <box marginTop={1}>
            <text><span fg={colors.text.muted}>{instructions ?? "Complete authorization in your browser."}</span></text>
          </box>
          {url && (
            <box marginTop={1} flexDirection="column">
              <text><span fg={colors.text.disabled}>Fallback URL</span></text>
              <text><span fg={colors.text.muted}>{url}</span></text>
            </box>
          )}
          <box marginTop={1}>
            <text><span fg={colors.status.warning}>Waiting for authorization...</span></text>
          </box>
          {error && (
            <box marginTop={1}>
              <text><span fg={colors.status.error}>{error}</span></text>
            </box>
          )}
        </box>
      )}
    </Dialog>
  );
}
