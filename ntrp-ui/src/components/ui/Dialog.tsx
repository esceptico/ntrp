import React from "react";
import { RGBA } from "@opentui/core";
import { useDimensions } from "../../contexts/index.js";
import { colors, useThemeVersion } from "./colors.js";

const OVERLAY_BG = RGBA.fromInts(0, 0, 0, 150);

interface DialogProps {
  title: string;
  size?: "medium" | "large" | "full";
  onClose: () => void;
  closable?: boolean;
  footer?: React.ReactNode;
  children: (dims: { width: number; height: number }) => React.ReactNode;
}

export function Dialog({ title, size = "medium", closable = true, footer, children }: DialogProps) {
  useThemeVersion();
  const { width: W, height: H } = useDimensions();

  const dialogW = size === "full" ? W - 8 : size === "large" ? Math.min(80, W - 4) : Math.min(60, W - 4);
  const contentW = dialogW - 4;
  const contentMaxH = Math.max(
    3,
    size === "full" ? H - 10 : size === "large" ? H - 12 : Math.floor(H * 0.55) - 4,
  );
  const paddingTop = size === "full" ? 2 : size === "large" ? 2 : Math.max(1, Math.floor(H / 5));

  return (
    <box position="absolute" top={0} left={0} width={W} height={H} backgroundColor={colors.background.base != null ? OVERLAY_BG : undefined}>
      <box alignItems="center" paddingTop={paddingTop}>
        <box
          width={dialogW}
          maxWidth={W - 2}
          backgroundColor={colors.background.element ?? colors.background.menu}
          border
          borderStyle="rounded"
          borderColor={colors.border}
        >
          <box flexShrink={0} paddingX={1} flexDirection="row" justifyContent="space-between">
            <text><span fg={colors.text.primary}><strong>{title}</strong></span></text>
            {closable && <text><span fg={colors.text.muted}>esc</span></text>}
          </box>
          <box paddingX={1}>
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
