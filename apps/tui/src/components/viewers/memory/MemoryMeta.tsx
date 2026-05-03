import { Fragment } from "react";

import { colors, truncateText } from "../../ui/index.js";

export interface MemoryMetaSegment {
  text: string | number;
  fg?: string;
  width?: number;
}

export interface MemoryMetaRow {
  label: string;
  value: string | number;
  labelFg?: string;
  valueFg?: string;
}

const META_SEPARATOR = " | ";

function cell(text: string, width: number): string {
  if (width <= 0) return "";
  return truncateText(text, width);
}

function segmentWidths(segments: MemoryMetaSegment[], width: number): number[] {
  const separatorWidth = Math.max(0, segments.length - 1) * META_SEPARATOR.length;
  const availableTextWidth = Math.max(0, width - separatorWidth);
  const widths = segments.map((segment) => {
    const textLength = String(segment.text).length;
    return Math.min(segment.width ?? textLength, textLength);
  });

  let overflow = widths.reduce((sum, segmentWidth) => sum + segmentWidth, 0) - availableTextWidth;
  while (overflow > 0) {
    let largestIndex = -1;
    let largestWidth = 0;
    for (let index = 0; index < widths.length; index += 1) {
      if (widths[index] > largestWidth) {
        largestWidth = widths[index];
        largestIndex = index;
      }
    }
    if (largestIndex < 0 || largestWidth <= 1) break;

    const shrinkBy = Math.min(overflow, largestWidth - 1);
    widths[largestIndex] -= shrinkBy;
    overflow -= shrinkBy;
  }

  return widths;
}

export function MemoryMetaLine({ segments, width }: { segments: MemoryMetaSegment[]; width: number }) {
  let used = 0;
  const visible = segments.filter((segment) => String(segment.text).trim().length > 0);
  const widths = segmentWidths(visible, width);

  return (
    <text>
      {visible.map((segment, index) => {
        const separator = index === 0 ? "" : META_SEPARATOR;
        const remainingBeforeSeparator = Math.max(0, width - used);
        if (remainingBeforeSeparator <= 0) return null;

        const separatorText = separator.slice(0, remainingBeforeSeparator);
        used += separatorText.length;

        const remaining = Math.max(0, width - used);
        if (remaining <= 0) {
          return <span key={index} fg={colors.text.disabled}>{separatorText}</span>;
        }

        const segmentWidth = Math.min(widths[index] ?? remaining, remaining);
        used += segmentWidth;

        return (
          <Fragment key={index}>
            {separatorText && <span fg={colors.text.disabled}>{separatorText}</span>}
            <span fg={segment.fg ?? colors.text.secondary}>{cell(String(segment.text), segmentWidth)}</span>
          </Fragment>
        );
      })}
    </text>
  );
}

function rowLabelWidth(rows: MemoryMetaRow[], width: number, provided?: number): number {
  const maxLabel = Math.max(1, ...rows.map((row) => row.label.length));
  return Math.max(1, Math.min(provided ?? maxLabel, Math.max(1, width - META_SEPARATOR.length - 1)));
}

export function MemoryMetaRows({
  title,
  rows,
  width,
  labelWidth,
  titleFg = colors.text.muted,
}: {
  title?: string;
  rows: MemoryMetaRow[];
  width: number;
  labelWidth?: number;
  titleFg?: string;
}) {
  if (rows.length === 0) return null;

  const labelColumn = rowLabelWidth(rows, width, labelWidth);
  const valueWidth = Math.max(1, width - labelColumn - META_SEPARATOR.length);

  return (
    <box flexDirection="column">
      {title && <text><span fg={titleFg}>{title}</span></text>}
      {rows.map((row, index) => (
        <text key={index}>
          <span fg={row.labelFg ?? colors.text.secondary}>{cell(row.label, labelColumn).padEnd(labelColumn)}</span>
          <span fg={colors.text.disabled}>{META_SEPARATOR}</span>
          <span fg={row.valueFg ?? colors.text.disabled}>{cell(String(row.value), valueWidth)}</span>
        </text>
      ))}
    </box>
  );
}
