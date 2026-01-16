import React from "react";
import { Text } from "ink";
import { colors, accentColors, truncateText, type AccentColor } from "../../ui/index.js";
import { BooleanItem, NumberItem, COL_CURSOR, COL_CHECK, COL_NUMBER, pad } from "./config.js";

export const colorOptions = Object.keys(accentColors) as AccentColor[];

interface RowProps {
  selected: boolean;
  accent: string;
}

interface BooleanRowProps extends RowProps {
  item: BooleanItem;
  value: boolean;
}

export function BooleanRow({ item, value, selected, accent }: BooleanRowProps) {
  const cursor = pad(selected ? ">" : "", COL_CURSOR);
  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{cursor}</Text>
      <Text color={value ? accent : colors.text.muted}>{pad(value ? "[✓]" : "[ ]", COL_CHECK)}</Text>
      <Text bold={selected} color={selected ? accent : colors.text.primary}>{item.description}</Text>
    </Text>
  );
}

interface ColorPickerProps extends RowProps {
  currentColor: AccentColor;
}

export function ColorPicker({ currentColor, selected, accent }: ColorPickerProps) {
  const cursor = pad(selected ? ">" : "", COL_CURSOR);
  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{cursor}</Text>
      <Text color={colors.text.muted}>Accent </Text>
      {colorOptions.map((color, idx) => {
        const isCurrent = currentColor === color;
        return (
          <Text key={color}>
            <Text color={accentColors[color].primary} bold={isCurrent}>
              {isCurrent ? `[${color}]` : color}
            </Text>
            {idx < colorOptions.length - 1 && <Text color={colors.text.muted}> </Text>}
          </Text>
        );
      })}
    </Text>
  );
}

interface ModelRowProps extends RowProps {
  model: string;
  isCurrent: boolean;
  maxWidth: number;
}

export function ModelRow({ model, isCurrent, selected, accent, maxWidth }: ModelRowProps) {
  const cursor = pad(selected ? ">" : "", COL_CURSOR);
  const shortName = model.split("/").pop() || model;
  const displayName = truncateText(shortName, maxWidth);
  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{cursor}</Text>
      <Text color={isCurrent ? accent : colors.text.secondary} bold={isCurrent}>
        {isCurrent ? `[${displayName}]` : ` ${displayName} `}
      </Text>
    </Text>
  );
}

interface NumberRowProps extends RowProps {
  item: NumberItem;
  value: number;
}

export function NumberRow({ item, value, selected, accent }: NumberRowProps) {
  const cursor = pad(selected ? ">" : "", COL_CURSOR);
  return (
    <Text>
      <Text color={selected ? accent : colors.text.disabled}>{cursor}</Text>
      <Text color={selected ? accent : colors.text.secondary}>{pad(`← ${value} →`, COL_NUMBER)}</Text>
      <Text bold={selected} color={selected ? accent : colors.text.primary}>{item.description} ({item.min}–{item.max})</Text>
    </Text>
  );
}
