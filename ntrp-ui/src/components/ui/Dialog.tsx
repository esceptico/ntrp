import React from "react";
import { RGBA } from "@opentui/core";
import { useDimensions } from "../../contexts/index.js";
import { colors } from "./colors.js";

interface DialogProps {
  title: string;
  size?: "medium" | "large" | "full";
  onClose: () => void;
  closable?: boolean;
  footer?: React.ReactNode;
  children: (dims: { width: number; height: number }) => React.ReactNode;
}

export function Dialog({ title, size = "medium", closable = true, footer, children }: DialogProps) {
  const { width: W, height: H } = useDimensions();

  let maxW: number;
  let maxH: number;
  switch (size) {
    case "medium":
      maxW = Math.min(60, W - 4);
      maxH = Math.min(20, H - 6);
      break;
    case "large":
      maxW = Math.min(80, W - 4);
      maxH = Math.min(30, H - 4);
      break;
    case "full":
      maxW = W - 8;
      maxH = H - 4;
      break;
  }

  const offsetY = Math.max(1, Math.floor((H - maxH) / 2));
  const contentW = maxW - 4;
  const contentMaxH = maxH - 3 - (footer ? 1 : 0);

  return (
    <box position="absolute" top={0} left={0} width={W} height={H} backgroundColor={RGBA.fromInts(0, 0, 0, 150)}>
      <box alignItems="center" paddingTop={offsetY}>
        <box
          maxWidth={maxW}
          maxHeight={maxH}
          backgroundColor={colors.background.element}
          border
          borderStyle="rounded"
          borderColor={colors.border}
        >
          <box flexShrink={0} paddingX={1} flexDirection="row" justifyContent="space-between">
            <text><span fg={colors.text.primary}><strong>{title}</strong></span></text>
            {closable && <text><span fg={colors.text.muted}>esc</span></text>}
          </box>
          <box flexGrow={1} overflow="hidden" paddingX={1} maxHeight={contentMaxH}>
            {children({ width: contentW, height: contentMaxH })}
          </box>
          {footer && (
            <box flexShrink={0} paddingX={1}>
              {footer}
            </box>
          )}
        </box>
      </box>
    </box>
  );
}
