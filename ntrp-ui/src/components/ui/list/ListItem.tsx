import React from "react";
import { Text } from "ink";
import { truncateText } from "../../../lib/utils.js";
import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface ListItemProps {
  selected?: boolean;
  icon?: string;
  iconColor?: string;
  label: string;
  detail?: string;
  detailColor?: string;
  suffix?: string;
  suffixColor?: string;
  maxLabelWidth?: number;
}

export function ListItem({
  selected = false,
  icon,
  iconColor,
  label,
  detail,
  detailColor,
  suffix,
  suffixColor,
  maxLabelWidth,
}: ListItemProps) {
  const contentWidth = useContentWidth();

  const prefixWidth = 2;
  const iconWidth = icon ? 2 : 0;
  const detailWidth = detail ? detail.length + 1 : 0;
  const suffixWidth = suffix ? suffix.length + 1 : 0;
  const availableForLabel = contentWidth - prefixWidth - iconWidth - detailWidth - suffixWidth;
  const labelWidth = maxLabelWidth ? Math.min(maxLabelWidth, availableForLabel) : availableForLabel;

  const truncatedLabel = truncateText(label, Math.max(0, labelWidth));

  return (
    <Text>
      <Text color={selected ? colors.selection.indicator : colors.text.disabled}>
        {selected ? "> " : "  "}
      </Text>
      {icon && (
        <Text color={selected ? colors.selection.active : (iconColor || colors.status.success)}>
          {icon}{" "}
        </Text>
      )}
      <Text color={selected ? colors.list.itemTextSelected : colors.list.itemText} bold={selected}>
        {truncatedLabel}
      </Text>
      {detail && (
        <Text color={detailColor || colors.list.itemDetail}> {detail}</Text>
      )}
      {suffix && (
        <Text color={suffixColor || colors.list.itemDetail}> {suffix}</Text>
      )}
    </Text>
  );
}
