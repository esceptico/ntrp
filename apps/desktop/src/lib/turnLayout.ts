export interface TurnLayoutInput {
  children: TurnLayoutChild[];
  isDone: boolean;
}

export interface TurnLayoutChild {
  id: string;
  role: string | null;
}

export interface TurnLayoutResult {
  workIds: string[];
  afterWorkIds: string[];
  finalAssistantId: string | null;
}

export function turnLayout({
  children,
  isDone,
}: TurnLayoutInput): TurnLayoutResult {
  const childIds = children.map((child) => child.id);
  const lastAssistantId = () => {
    for (let i = children.length - 1; i >= 0; i--) {
      if (children[i].role === "assistant") return children[i].id;
    }
    return null;
  };

  if (!isDone) {
    return {
      workIds: [],
      afterWorkIds: childIds,
      finalAssistantId: lastAssistantId(),
    };
  }

  const firstActivityIndex = children.findIndex((child) => child.role === "activity");
  if (firstActivityIndex < 0) {
    return {
      workIds: [],
      afterWorkIds: childIds,
      finalAssistantId: lastAssistantId(),
    };
  }

  const lastIndex = children.length - 1;
  const finalAssistantIndex = children[lastIndex]?.role === "assistant" ? lastIndex : -1;

  if (finalAssistantIndex < 0) {
    return {
      workIds: childIds,
      afterWorkIds: [],
      finalAssistantId: null,
    };
  }

  return {
    workIds: childIds.filter((_, index) => index !== finalAssistantIndex),
    afterWorkIds: [children[finalAssistantIndex].id],
    finalAssistantId: children[finalAssistantIndex].id,
  };
}
