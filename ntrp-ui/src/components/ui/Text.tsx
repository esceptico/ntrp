import React from "react";
import { Box, Text } from "ink";
import { truncateText } from "../../lib/utils.js";
import { useContentWidth } from "../../contexts/index.js";
import { colors } from "./colors.js";

interface ConstrainedTextProps {
  children: string;
  width?: number;
  wrap?: 'wrap' | 'truncate' | 'truncate-end' | 'truncate-middle' | 'truncate-start';
  color?: string;
  bold?: boolean;
  dimColor?: boolean;
}

export function ConstrainedText({
  children,
  width,
  wrap = 'wrap',
  color,
  bold,
  dimColor,
}: ConstrainedTextProps) {
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  let content = children;
  if (wrap === 'truncate' || wrap === 'truncate-end') {
    content = truncateText(children, effectiveWidth, 'end');
  } else if (wrap === 'truncate-middle') {
    content = truncateText(children, effectiveWidth, 'middle');
  } else if (wrap === 'truncate-start') {
    content = truncateText(children, effectiveWidth, 'start');
  }

  return (
    <Box width={effectiveWidth} overflow="hidden">
      <Text color={color} bold={bold} dimColor={dimColor} wrap={wrap === 'wrap' ? 'wrap' : 'truncate'}>
        {content}
      </Text>
    </Box>
  );
}

interface HelpTextProps {
  children: React.ReactNode;
}

export function HelpText({ children }: HelpTextProps) {
  return <Text color={colors.text.muted}>{children}</Text>;
}
