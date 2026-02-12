import React from "react";
import { useDimensions } from "../../contexts/index.js";
import { colors } from "./colors.js";

interface DialogProps {
  title: string;
  size: "medium" | "large" | "full";
  onClose: () => void;
  footer?: React.ReactNode;
  children: (dims: { width: number; height: number }) => React.ReactNode;
}

export function Dialog({ title, size, footer, children }: DialogProps) {
  const { width: W, height: H } = useDimensions();

  let dialogW: number;
  let dialogH: number;
  switch (size) {
    case "medium":
      dialogW = Math.min(60, W - 4);
      dialogH = Math.min(20, H - 6);
      break;
    case "large":
      dialogW = Math.min(80, W - 4);
      dialogH = Math.min(30, H - 4);
      break;
    case "full":
      dialogW = W - 8;
      dialogH = H - 4;
      break;
  }

  const offsetY = Math.floor((H - dialogH) / 3);
  const contentW = dialogW - 4;
  const contentH = dialogH - 3 - (footer ? 1 : 0);

  return (
    <box position="absolute" top={0} left={0} width={W} height={H}>
      <box alignItems="center" paddingTop={offsetY}>
        <box
          width={dialogW}
          height={dialogH}
          backgroundColor={colors.background.element}
          border
          borderStyle="rounded"
          borderColor={colors.border}
        >
          <box flexShrink={0} paddingX={1} flexDirection="row" justifyContent="space-between">
            <text><span fg={colors.text.primary}><strong>{title}</strong></span></text>
            <text><span fg={colors.text.muted}>esc close</span></text>
          </box>
          <box flexGrow={1} overflow="hidden" paddingX={1} height={contentH}>
            {children({ width: contentW, height: contentH })}
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
