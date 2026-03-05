import { Status, type Status as StatusType } from "../../lib/constants.js";
import { colors } from "../ui/colors.js";
import { BraillePendulum, BrailleCompress, BrailleSort, CyclingStatus } from "../ui/spinners/index.js";

export interface InputFooterProps {
  isStreaming: boolean;
  status: StatusType;
  accentValue: string;
  escHint: boolean;
  copiedFlash: boolean;
  indexStatus?: {
    indexing: boolean;
    progress: { total: number; done: number };
    reembedding?: boolean;
    reembed_progress?: { total: number; done: number } | null;
  } | null;
}

export function InputFooter({ isStreaming, status, accentValue, escHint, copiedFlash, indexStatus }: InputFooterProps) {
  if (isStreaming || status === Status.COMPRESSING) {
    return (
      <box flexDirection="row" justifyContent="space-between">
        <box flexDirection="row" gap={1} flexGrow={1}>
          <box marginLeft={1}>
            {status === Status.COMPRESSING ? (
              <BrailleCompress width={8} color={accentValue} interval={30} />
            ) : (
              <BraillePendulum width={8} color={accentValue} spread={1} interval={20} />
            )}
          </box>
          {status === Status.COMPRESSING ? (
            <text><span fg={colors.text.muted}>compressing context</span></text>
          ) : (
            <CyclingStatus status={status} isStreaming={isStreaming} />
          )}
        </box>
        {isStreaming && (
          <text>
            <span fg={colors.footer}>esc</span>
            <span fg={colors.text.disabled}> interrupt</span>
          </text>
        )}
      </box>
    );
  }

  return (
    <box flexDirection="row" justifyContent="space-between">
      <box flexDirection="row" marginLeft={3}>
        {indexStatus?.indexing || indexStatus?.reembedding ? (
          <box flexDirection="row" gap={1}>
            <BrailleSort width={8} color={accentValue} interval={40} />
            <text><span fg={colors.text.muted}>{indexStatus.reembedding ? "re-embedding" : "indexing"}</span></text>
          </box>
        ) : null}
        <text>
          {copiedFlash ? (
            <span fg={colors.text.muted}>Copied to clipboard</span>
          ) : escHint ? (
            <span fg={accentValue}>esc again to clear</span>
          ) : null}
        </text>
      </box>
      <box gap={2} flexDirection="row">
        <text>
          <span fg={colors.footer}>ctrl+n</span>
          <span fg={colors.text.disabled}> new chat</span>
        </text>
        <text>
          <span fg={colors.footer}>ctrl+l</span>
          <span fg={colors.text.disabled}> side panel</span>
        </text>
        <text>
          <span fg={colors.footer}>tab tab</span>
          <span fg={colors.text.disabled}> approvals</span>
        </text>
        <text>
          <span fg={colors.footer}>shift+tab</span>
          <span fg={colors.text.disabled}> switch chat</span>
        </text>
      </box>
    </box>
  );
}
