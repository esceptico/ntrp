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

  // The final answer is the last assistant message that appears after work
  // has started, even if a late/replayed activity row lands after it.
  // Otherwise a completed historic turn can hide the user's actual answer
  // inside the collapsed "Worked" block just because a tool/activity event
  // was appended after the text during history/replay reconstruction.
  let finalAssistantIndex = -1;
  for (let i = children.length - 1; i > firstActivityIndex; i--) {
    if (children[i].role === "assistant") {
      finalAssistantIndex = i;
      break;
    }
  }

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
