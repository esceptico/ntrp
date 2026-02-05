import { Text } from "ink";
import { colors, accentColors, type AccentColor } from "../../ui/index.js";
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
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{selected ? "› " : "  "}</Text>
      <Text color={value ? accent : colors.text.muted}>{value ? "[•] " : "[ ] "}</Text>
      <Text color={selected ? colors.text.primary : colors.text.secondary}>{item.label}</Text>
    </Text>
  );
}

interface ColorPickerProps extends RowProps {
  currentColor: AccentColor;
}

export function ColorPicker({ currentColor, selected, accent }: ColorPickerProps) {
  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{selected ? "› " : "  "}</Text>
      <Text color={colors.text.secondary}>Accent  </Text>
      {colorOptions.map((color, idx) => {
        const isCurrent = currentColor === color;
        return (
          <Text key={color}>
            <Text color={accentColors[color].primary} inverse={isCurrent}>
              {isCurrent ? ` ${color} ` : ` ${color} `}
            </Text>
          </Text>
        );
      })}
    </Text>
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

  // Build slider track
  const before = "─".repeat(position);
  const after = "─".repeat(sliderWidth - 1 - position);
  const knob = "●";

  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{selected ? "› " : "  "}</Text>
      <Text color={selected ? colors.text.primary : colors.text.secondary}>{label}</Text>
      <Text color={selected ? accent : colors.text.primary} bold>{String(value).padStart(2)}</Text>
      <Text color={colors.text.muted}>  [</Text>
      <Text color={colors.text.disabled}>{before}</Text>
      <Text color={selected ? accent : colors.text.primary}>{knob}</Text>
      <Text color={colors.text.disabled}>{after}</Text>
      <Text color={colors.text.muted}>]  </Text>
      <Text color={colors.text.disabled}>({item.min}..{item.max})</Text>
    </Text>
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
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{selected ? "› " : "  "}</Text>
      <Text color={selected ? colors.text.primary : colors.text.secondary}>{paddedLabel}</Text>
      <Text color={colors.text.muted}>[</Text>
      <Text color={selected ? accent : colors.text.primary}> {displayName} </Text>
      <Text color={colors.text.muted}>▾]</Text>
    </Text>
  );
}
