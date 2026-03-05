import { colors, SelectionIndicator } from "../../ui/index.js";
import type { NumberItem } from "./config.js";

const LABEL_WIDTH = 14;

interface ModelSelectorProps {
  label: string;
  currentModel: string;
  selected: boolean;
  accent: string;
  maxWidth: number;
}

export function ModelSelector({ label, currentModel, selected, accent, maxWidth }: ModelSelectorProps) {
  const truncated = currentModel.length > maxWidth ? currentModel.slice(0, maxWidth - 1) + "…" : currentModel;
  return (
    <text>
      <SelectionIndicator selected={selected} accent={accent} />
      <span fg={selected ? colors.text.primary : colors.text.secondary}>{label.padEnd(LABEL_WIDTH)}</span>
      <span fg={selected ? accent : colors.text.muted}>{truncated}</span>
    </text>
  );
}

interface RowProps {
  selected: boolean;
  accent: string;
}

interface NumberRowProps extends RowProps {
  item: NumberItem;
  value: number;
  sliderWidth?: number;
}

export function NumberRow({ item, value, selected, accent, sliderWidth = 16 }: NumberRowProps) {
  const label = item.label.padEnd(LABEL_WIDTH + 4);
  const range = item.max - item.min;
  const position = Math.round(((value - item.min) / range) * (sliderWidth - 1));

  const before = "─".repeat(position);
  const after = "─".repeat(sliderWidth - 1 - position);
  const knob = "●";

  return (
    <text>
      <SelectionIndicator selected={selected} accent={accent} />
      <span fg={selected ? colors.text.primary : colors.text.secondary}>{label}</span>
      <span fg={selected ? accent : colors.text.primary}><strong>{String(value).padStart(2)}</strong></span>
      <span fg={colors.text.muted}>  [</span>
      <span fg={colors.text.disabled}>{before}</span>
      <span fg={selected ? accent : colors.text.primary}>{knob}</span>
      <span fg={colors.text.disabled}>{after}</span>
      <span fg={colors.text.muted}>]  </span>
      <span fg={colors.text.disabled}>({item.min}..{item.max})</span>
    </text>
  );
}

