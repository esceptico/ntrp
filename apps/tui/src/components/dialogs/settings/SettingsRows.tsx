import { colors, SelectionIndicator } from "../../ui/index.js";
import type { NumberItem } from "./config.js";
import type { AgentSettings } from "../../../hooks/useSettings.js";

const LABEL_WIDTH = 18;
const INDICATOR_WIDTH = 2;

export function Header({ children, first }: { children: string; first?: boolean }) {
  return (
    <box marginLeft={INDICATOR_WIDTH} marginTop={first ? 0 : 1}>
      <text><span fg={colors.selection.active}><strong>{children}</strong></span></text>
    </box>
  );
}

export function Row({ selected, accent, label, labelWidth = LABEL_WIDTH, arrow, children }: {
  selected: boolean;
  accent: string;
  label?: string;
  labelWidth?: number;
  arrow?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <box flexDirection="row">
      <box width={INDICATOR_WIDTH} flexShrink={0}>
        {arrow ? (
          <text><span fg={selected ? accent : colors.text.disabled}>{selected ? "> " : "  "}</span></text>
        ) : (
          <text><SelectionIndicator selected={selected} accent={accent} /></text>
        )}
      </box>
      {label != null && (
        <box width={labelWidth} flexShrink={0}>
          <text><span fg={selected ? colors.text.primary : colors.text.secondary}>{label}</span></text>
        </box>
      )}
      {children}
    </box>
  );
}

export function StatusMessage({ children, color }: { children: string; color: string }) {
  return (
    <box marginTop={1} marginLeft={INDICATOR_WIDTH}>
      <text><span fg={color}>{children}</span></text>
    </box>
  );
}

export function FormField({ label, active, children, labelWidth = 12 }: {
  label: string;
  active: boolean;
  children: React.ReactNode;
  labelWidth?: number;
}) {
  return (
    <box flexDirection="row">
      <box width={labelWidth} flexShrink={0}>
        <text><span fg={active ? colors.text.primary : colors.text.secondary}>{label}</span></text>
      </box>
      {children}
    </box>
  );
}

interface RowProps {
  selected: boolean;
  accent: string;
  header?: string;
  firstHeader?: boolean;
  id?: string;
}

export function ModelSelector({ label, currentModel, selected, accent, maxWidth }: {
  label: string;
  currentModel: string;
  selected: boolean;
  accent: string;
  maxWidth: number;
}) {
  const truncated = currentModel.length > maxWidth ? currentModel.slice(0, maxWidth - 1) + "…" : currentModel;
  return (
    <Row selected={selected} accent={accent} label={label}>
      <text><span fg={selected ? accent : colors.text.muted}>{truncated}</span></text>
    </Row>
  );
}

export function NumberRow({ item, value, selected, accent, valueWidth, sliderWidth = 16, showDescription, header, firstHeader, id }: RowProps & {
  item: NumberItem;
  value: number;
  valueWidth?: number;
  sliderWidth?: number;
  showDescription?: boolean;
}) {
  const vw = valueWidth ?? String(item.max).length;
  const range = item.max - item.min;
  const position = Math.round(((value - item.min) / range) * (sliderWidth - 1));

  return (
    <box flexDirection="column" id={id}>
      {header && <Header first={firstHeader}>{header}</Header>}
      <Row selected={selected} accent={accent} label={item.label}>
        <text>
          <span fg={selected ? accent : colors.text.primary}><strong>{String(value).padStart(vw)}</strong></span>
          <span fg={colors.text.muted}>  [</span>
          <span fg={colors.text.disabled}>{"─".repeat(position)}</span>
          <span fg={selected ? accent : colors.text.primary}>●</span>
          <span fg={colors.text.disabled}>{"─".repeat(sliderWidth - 1 - position)}</span>
          <span fg={colors.text.muted}>]  </span>
          <span fg={colors.text.disabled}>({item.min}..{item.max})</span>
        </text>
      </Row>
      {showDescription && item.description && (
        <box marginLeft={INDICATOR_WIDTH + LABEL_WIDTH}>
          <text><span fg={colors.text.disabled}>{item.description}</span></text>
        </box>
      )}
    </box>
  );
}

export function ToggleRow({ label, enabled, selected, accent, description, header, firstHeader, id }: RowProps & {
  label: string;
  enabled: boolean;
  description?: string;
}) {
  return (
    <box flexDirection="column" id={id}>
      {header && <Header first={firstHeader}>{header}</Header>}
      <Row selected={selected} accent={accent}>
        <text>
          <span fg={enabled ? (selected ? accent : colors.text.primary) : colors.text.muted}>
            {enabled ? "●" : "○"}
          </span>
          <span fg={selected ? colors.text.primary : colors.text.secondary}> {label}</span>
          {description && (
            <>
              <span fg={colors.text.disabled}> — </span>
              <span fg={enabled ? colors.text.primary : colors.text.muted}>{description}</span>
            </>
          )}
        </text>
      </Row>
    </box>
  );
}

export function CycleRow({ label, value, selected, accent, valueColor, header, firstHeader, id }: RowProps & {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <box flexDirection="column" id={id}>
      {header && <Header first={firstHeader}>{header}</Header>}
      <Row selected={selected} accent={accent} label={label || undefined}>
        <text>
          {selected && <span fg={colors.text.muted}>◂ </span>}
          <span fg={valueColor ?? (selected ? accent : colors.text.primary)}>{value}</span>
          {selected && <span fg={colors.text.muted}> ▸</span>}
        </text>
      </Row>
    </box>
  );
}

export function NumberListSection({ items, settings, selectedIndex, accent, header, firstHeader }: {
  items: NumberItem[];
  settings: AgentSettings;
  selectedIndex: number;
  accent: string;
  header?: string;
  firstHeader?: boolean;
}) {
  const valueWidth = Math.max(...items.map(i => String(i.max).length));
  return (
    <box flexDirection="column">
      {header && <Header first={firstHeader}>{header}</Header>}
      {items.map((item, idx) => (
        <NumberRow
          key={item.key}
          id={`item-${idx}`}
          item={item}
          value={settings[item.key as keyof AgentSettings] as number}
          valueWidth={valueWidth}
          selected={idx === selectedIndex}
          accent={accent}
          showDescription
        />
      ))}
    </box>
  );
}
