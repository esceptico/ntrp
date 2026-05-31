export interface SseFrameParser {
  /** Feed a decoded text chunk; returns parsed `data:` frame payloads in order. */
  push(chunk: string): unknown[];
}

export function createSseFrameParser(): SseFrameParser;
