export interface MessageSourceFocus {
  sessionId: string;
  messageStart: number;
  messageEnd: number;
  nonce: number;
}

export interface SourceIndexedMessage {
  sourceIndex?: number;
}

export function messageInSourceFocus(
  message: SourceIndexedMessage | null | undefined,
  focus: MessageSourceFocus | null | undefined,
  currentSessionId: string | null | undefined,
): boolean {
  if (!message || !focus || currentSessionId !== focus.sessionId) return false;
  if (message.sourceIndex === undefined) return false;
  return message.sourceIndex >= focus.messageStart && message.sourceIndex < focus.messageEnd;
}

export function firstMessageIdInSourceFocus<T extends SourceIndexedMessage>(
  order: string[],
  messages: Map<string, T>,
  focus: MessageSourceFocus | null | undefined,
  currentSessionId: string | null | undefined,
): string | null {
  if (!focus || currentSessionId !== focus.sessionId) return null;
  for (const id of order) {
    if (messageInSourceFocus(messages.get(id), focus, currentSessionId)) return id;
  }
  return null;
}
