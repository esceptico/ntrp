export interface MessageSourceFocus {
  sessionId: string;
  messageStart?: number;
  messageEnd?: number;
  messageStartId?: string;
  messageEndId?: string;
  nonce: number;
}

export interface SourceIndexedMessage {
  sourceIndex?: number;
  sourceMessageId?: string;
}

export function messageInSourceFocus(
  message: SourceIndexedMessage | null | undefined,
  focus: MessageSourceFocus | null | undefined,
  currentSessionId: string | null | undefined,
): boolean {
  if (!message || !focus || currentSessionId !== focus.sessionId) return false;
  if (focus.messageStartId && message.sourceMessageId) {
    if (message.sourceMessageId === focus.messageStartId) return true;
    if (focus.messageEndId && message.sourceMessageId === focus.messageEndId) return true;
  }
  if (focus.messageStart === undefined || focus.messageEnd === undefined) return false;
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
  if (focus.messageStartId) {
    for (const id of order) {
      if (messages.get(id)?.sourceMessageId === focus.messageStartId) return id;
    }
  }
  for (const id of order) {
    if (messageInSourceFocus(messages.get(id), focus, currentSessionId)) return id;
  }
  return null;
}

export function resolveMessageSourceFocus<T extends SourceIndexedMessage>(
  order: string[],
  messages: Map<string, T>,
  focus: MessageSourceFocus,
  currentSessionId: string | null | undefined,
): MessageSourceFocus {
  if (currentSessionId !== focus.sessionId || !focus.messageStartId) return focus;

  let start: number | undefined;
  let end: number | undefined;
  for (const id of order) {
    const message = messages.get(id);
    if (!message?.sourceMessageId || message.sourceIndex === undefined) continue;
    if (message.sourceMessageId === focus.messageStartId) {
      start = message.sourceIndex;
    }
    if (focus.messageEndId && message.sourceMessageId === focus.messageEndId) {
      end = message.sourceIndex + 1;
    }
  }

  if (start === undefined) return focus;
  return {
    ...focus,
    messageStart: start,
    messageEnd: end ?? start + 1,
  };
}
