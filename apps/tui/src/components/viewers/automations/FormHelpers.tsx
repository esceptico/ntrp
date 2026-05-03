import { colors } from "../../ui/index.js";

export const LABEL_WIDTH = 14;

export function labelCell(text: string, focused: boolean) {
  return (
    <box width={LABEL_WIDTH} flexShrink={0}>
      <text>
        <span fg={focused ? colors.selection.active : colors.text.disabled}>{focused ? ">" : " "}</span>
        <span fg={focused ? colors.text.primary : colors.text.muted}>{` ${text}`}</span>
      </text>
    </box>
  );
}

export function optionCell(opt: string, selected: boolean, focused: boolean) {
  const fg = selected
    ? (focused ? colors.text.primary : colors.text.secondary)
    : colors.text.disabled;
  return (
    <text key={opt}>
      <span fg={fg}>{selected ? `[${opt}]` : ` ${opt} `}</span>
    </text>
  );
}

export function dayCell(day: string, isSelected: boolean, isCursor: boolean) {
  const marker = isSelected ? "\u25CF" : "\u25CB";
  const fg = isSelected
    ? (isCursor ? colors.selection.active : colors.status.success)
    : (isCursor ? colors.text.primary : colors.text.disabled);
  return (
    <text key={day}>
      <span fg={fg}>{` ${marker} ${day} `}</span>
    </text>
  );
}

export function selectorRow(label: string, focused: boolean, options: readonly string[], selected: string) {
  return (
    <box flexDirection="row">
      {labelCell(label, focused)}
      <box flexDirection="row" flexWrap="wrap">
        {options.map((opt) => optionCell(opt, opt === selected, focused))}
      </box>
    </box>
  );
}
