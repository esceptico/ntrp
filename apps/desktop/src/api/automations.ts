import { apiWithConfig, type AppConfig } from "@/api/core";
import type {
  Automation,
  AutomationRun,
  AutomationSuggestion,
  CreateAutomationPayload,
  UpdateAutomationPayload,
} from "@/api/types";

export async function listAutomationsApi(config: AppConfig): Promise<Automation[]> {
  const r = await apiWithConfig<{ automations: Automation[] }>(config, "/automations");
  return r.automations;
}

export async function listAutomationRunsApi(
  config: AppConfig,
  taskId: string,
  limit = 30,
): Promise<AutomationRun[]> {
  const r = await apiWithConfig<{ runs: AutomationRun[] }>(
    config,
    `/automations/${encodeURIComponent(taskId)}/runs?limit=${limit}`,
  );
  return r.runs;
}

export async function createAutomationApi(
  config: AppConfig,
  payload: CreateAutomationPayload,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, "/automations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAutomationApi(
  config: AppConfig,
  taskId: string,
  patch: UpdateAutomationPayload,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, `/automations/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function toggleAutomationApi(
  config: AppConfig,
  taskId: string,
): Promise<Automation> {
  return apiWithConfig<Automation>(config, `/automations/${encodeURIComponent(taskId)}/toggle`, {
    method: "POST",
  });
}

export async function runAutomationApi(config: AppConfig, taskId: string): Promise<void> {
  await apiWithConfig(config, `/automations/${encodeURIComponent(taskId)}/run`, { method: "POST" });
}

export async function deleteAutomationApi(config: AppConfig, taskId: string): Promise<void> {
  await apiWithConfig(config, `/automations/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}

// ─── Automation suggestions ──────────────────────────────────────────

export async function listAutomationSuggestionsApi(config: AppConfig): Promise<AutomationSuggestion[]> {
  const r = await apiWithConfig<{ suggestions: AutomationSuggestion[] }>(config, "/automations/suggestions");
  return r.suggestions;
}

export async function dismissAutomationSuggestionApi(config: AppConfig, id: string): Promise<void> {
  await apiWithConfig(config, `/automations/suggestions/${encodeURIComponent(id)}/dismiss`, {
    method: "POST",
  });
}

export async function refreshAutomationSuggestionsApi(config: AppConfig): Promise<AutomationSuggestion[]> {
  const r = await apiWithConfig<{ suggestions: AutomationSuggestion[] }>(config, "/automations/suggestions/refresh", {
    method: "POST",
  });
  return r.suggestions;
}

/** Convert a suggestion into the editor's create payload. Flattens the
 *  first trigger into the schedule fields `formFromPreset` expects, so the
 *  existing automation editor hydrates unchanged. */
export function suggestionToPayload(s: AutomationSuggestion): CreateAutomationPayload {
  const trigger = s.triggers[0];
  const schedule =
    trigger.type === "event"
      ? { trigger_type: "event" as const, event_type: trigger.event_type, lead_minutes: trigger.lead_minutes }
      : { trigger_type: "time" as const, at: trigger.at, days: trigger.days, every: trigger.every };
  return {
    name: s.name,
    description: s.description,
    from_suggestion_id: s.id,
    ...schedule,
  };
}
