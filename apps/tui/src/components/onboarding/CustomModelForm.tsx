import React from "react";
import { Dialog, colors, Hints } from "../ui/index.js";
import { TextInputField } from "../ui/input/TextInputField.js";

interface CustomPreset {
  name: string;
  base_url: string;
  needs_key: boolean;
}

export const CUSTOM_PRESETS: CustomPreset[] = [
  { name: "Ollama", base_url: "http://localhost:11434/v1", needs_key: false },
  { name: "vLLM", base_url: "http://localhost:8000/v1", needs_key: false },
  { name: "OpenRouter", base_url: "https://openrouter.ai/api/v1", needs_key: true },
  { name: "LM Studio", base_url: "http://localhost:1234/v1", needs_key: false },
  { name: "Together", base_url: "https://api.together.xyz/v1", needs_key: true },
  { name: "Other", base_url: "", needs_key: false },
];

export type CustomField = "preset" | "baseUrl" | "modelId" | "apiKey" | "contextWindow";
export const CUSTOM_FIELDS: CustomField[] = ["preset", "baseUrl", "modelId", "apiKey", "contextWindow"];

export interface CustomModelFormProps {
  customField: CustomField;
  presetIndex: number;
  baseUrl: string;
  baseUrlCursor: number;
  modelId: string;
  modelIdCursor: number;
  customApiKey: string;
  customApiKeyCursor: number;
  contextWindow: string;
  contextWindowCursor: number;
  saving: boolean;
  error: string | null;
  onBack: () => void;
}

export function CustomModelForm({
  customField, presetIndex,
  baseUrl, baseUrlCursor,
  modelId, modelIdCursor,
  customApiKey, customApiKeyCursor,
  contextWindow, contextWindowCursor,
  saving, error, onBack,
}: CustomModelFormProps) {
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
    <Dialog title="ADD CUSTOM MODEL" size="medium" onClose={onBack} closable footer={footer}>
      {() => (
        <box flexDirection="column">
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
}
