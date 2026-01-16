import React, { useCallback, useState } from "react";
import { Box, Text, type DOMElement } from "ink";
import { useContentWidth } from "../../../contexts/index.js";

interface MaxSizedBoxProps {
  children: React.ReactNode;
  maxHeight?: number;
  width?: number;
  overflowDirection?: 'top' | 'bottom';
  overflowLabel?: string;
}

export function MaxSizedBox({
  children,
  maxHeight,
  width,
  overflowDirection = 'bottom',
  overflowLabel = 'lines hidden',
}: MaxSizedBoxProps) {
  const [contentHeight, setContentHeight] = useState(0);
  const contentWidth = useContentWidth();
  const effectiveWidth = width ?? contentWidth;

  const ref = useCallback((node: DOMElement | null) => {
    if (!node || maxHeight === undefined) return;

    const measure = () => {
      const yoga = node.yogaNode;
      if (yoga) {
        setContentHeight(yoga.getComputedHeight());
      }
    };

    measure();
    const interval = setInterval(measure, 100);
    return () => clearInterval(interval);
  }, [maxHeight]);

  const isOverflowing = maxHeight !== undefined && contentHeight > maxHeight;
  const hiddenLines = isOverflowing ? Math.ceil(contentHeight - maxHeight) : 0;

  if (maxHeight === undefined) {
    return <Box width={effectiveWidth}>{children}</Box>;
  }

  return (
    <Box flexDirection="column" width={effectiveWidth}>
      {isOverflowing && overflowDirection === 'top' && (
        <Text dimColor>... {hiddenLines} {overflowLabel} above ...</Text>
      )}

      <Box height={maxHeight} overflow="hidden">
        <Box ref={ref} flexShrink={0} flexDirection="column">
          {children}
        </Box>
      </Box>

      {isOverflowing && overflowDirection === 'bottom' && (
        <Text dimColor>... {hiddenLines} {overflowLabel} below ...</Text>
      )}
    </Box>
  );
}
