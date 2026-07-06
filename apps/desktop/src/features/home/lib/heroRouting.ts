/** Suggestion the hero input can route to on Enter/selection. `kind:"chat"`
 *  is always present and always first — Enter with no explicit selection
 *  starts a chat with the raw query, so typing never "blocks" on a match. */
export interface HeroSuggestion {
  kind: "chat" | "slice" | "session" | "automation" | "skill";
  label: string;
  ref: string;
}

export interface HeroRoutingContext {
  sessions: { session_id: string; name: string | null }[];
  slices: { key: string; title: string }[];
  automations: { task_id: string; name: string }[];
  skills: { name: string; description: string }[];
}

const MAX_SUGGESTIONS = 6;

function matches(haystack: string, query: string): boolean {
  return haystack.toLowerCase().includes(query.toLowerCase());
}

/** Case-insensitive substring match across slices, sessions, automations,
 *  skills — ordered chat → slice → session → automation → skill, capped at
 *  `MAX_SUGGESTIONS`. Pure function; heroRouting owns its own suggestion
 *  model rather than reusing chat's commands.ts (feature isolation). */
export function routeHeroInput(query: string, ctx: HeroRoutingContext): HeroSuggestion[] {
  const suggestions: HeroSuggestion[] = [{ kind: "chat", label: query, ref: "" }];
  if (!query) return suggestions;

  for (const slice of ctx.slices) {
    if (matches(slice.title, query) || matches(slice.key, query)) {
      suggestions.push({ kind: "slice", label: slice.title, ref: slice.key });
    }
  }
  for (const session of ctx.sessions) {
    if (session.name && matches(session.name, query)) {
      suggestions.push({ kind: "session", label: session.name, ref: session.session_id });
    }
  }
  for (const automation of ctx.automations) {
    if (matches(automation.name, query)) {
      suggestions.push({ kind: "automation", label: automation.name, ref: automation.task_id });
    }
  }
  for (const skill of ctx.skills) {
    if (matches(skill.name, query)) {
      suggestions.push({ kind: "skill", label: skill.name, ref: skill.name });
    }
  }

  return suggestions.slice(0, MAX_SUGGESTIONS);
}
