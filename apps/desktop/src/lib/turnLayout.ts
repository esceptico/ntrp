export interface TurnLayoutInput {
  childIds: string[];
  finalAssistantId: string | null;
  isDone: boolean;
}

export interface TurnLayoutResult {
  directIds: string[];
  workIds: string[];
  finalAssistantId: string | null;
}

export function turnLayout({
  childIds,
  finalAssistantId,
  isDone,
}: TurnLayoutInput): TurnLayoutResult {
  if (!isDone) {
    return { directIds: childIds, workIds: [], finalAssistantId };
  }

  return {
    directIds: finalAssistantId ? [finalAssistantId] : [],
    workIds: finalAssistantId ? childIds.filter((id) => id !== finalAssistantId) : childIds,
    finalAssistantId,
  };
}
