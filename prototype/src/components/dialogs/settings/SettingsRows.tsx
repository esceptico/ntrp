import { colors, accentColors, type AccentColor, SelectionIndicator } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { BooleanItem, NumberItem } from "./config.js";

export const colorOptions = Object.keys(accentColors) as AccentColor[];

const LABEL_WIDTH = 14;

interface RowProps {
  selected: boolean;
  accent: string;
}

interface BooleanRowProps extends RowProps {
  item: BooleanItem;
  value: boolean;
}

export function BooleanRow({ item, value, selected, accent }: BooleanRowProps) {
  return (
    <text>
      <SelectionIndicator selected={selected} accent={accent} />
      <span fg={value ? accent : colors.text.muted}>{value ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED}</span>
      <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.label}</span>
    </text>
  );
}

interface ColorPickerProps extends RowProps {
  currentColor: AccentColor;
}

export function ColorPicker({ currentColor, selected, accent }: ColorPickerProps) {
  return (
    <text>
      <SelectionIndicator selected={selected} accent={accent} />
      <span fg={colors.text.secondary}>Accent  </span>
      {colorOptions.map((color) => {
        const isCurrent = currentColor === color;
        return isCurrent ? (
          <span key={color} bg={accentColors[color].primary} fg="#000000"> {color} </span>
        ) : (
          <span key={color} fg={accentColors[color].primary}> {color} </span>
        );
      })}
    </text>
  );
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

interface ModelSelectorProps extends RowProps {
  label: string;
  currentModel: string;
  maxWidth: number;
}

export function ModelSelector({ label, currentModel, selected, accent, maxWidth }: ModelSelectorProps) {
  const model = currentModel || "";
  const shortName = model.split("/").pop() || model || "—";
  const displayName = shortName.length > maxWidth ? shortName.slice(0, maxWidth - 3) + "..." : shortName;
  const paddedLabel = label.padEnd(LABEL_WIDTH);

  return (
    <text>
      <SelectionIndicator selected={selected} accent={accent} />
      <span fg={selected ? colors.text.primary : colors.text.secondary}>{paddedLabel}</span>
      <span fg={colors.text.muted}>[</span>
      <span fg={selected ? accent : colors.text.primary}> {displayName} </span>
      <span fg={colors.text.muted}>▾]</span>
    </text>
  );
}
