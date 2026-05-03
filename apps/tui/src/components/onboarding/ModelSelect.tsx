import React from "react";
import { Dialog, colors, SelectList, type SelectOption } from "../ui/index.js";

export interface ModelSelectProps {
  modelList: string[];
  saving: boolean;
  isActive: boolean;
  error: string | null;
  onSelect: (model: string) => void;
  onBack: () => void;
}

export function ModelSelect({ modelList, saving, isActive, error, onSelect, onBack }: ModelSelectProps) {
  const modelOptions: SelectOption[] = modelList.map(m => ({ value: m, title: m }));
  const footer = saving ? <text><span fg={colors.text.muted}>Saving...</span></text> : undefined;

  return (
    <Dialog title="DEFAULT CHAT MODEL" size="medium" onClose={onBack} closable footer={footer}>
      {({ height }) => (
        <box flexDirection="column">
          <SelectList
            options={modelOptions}
            visibleLines={height}
            isActive={isActive && !saving}
            onSelect={(opt) => onSelect(opt.value)}
            onClose={onBack}
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
}
