import {
  createAutomationApi,
  deleteAutomationApi,
  dismissAutomationSuggestionApi,
  listAutomationSuggestionsApi,
  listAutomationsApi,
  refreshAutomationSuggestionsApi,
  runAutomationApi,
  toggleAutomationApi,
  updateAutomationApi,
  type CreateAutomationPayload,
  type UpdateAutomationPayload,
} from "../api";
import { getState } from "../store";

export async function fetchAutomations(): Promise<void> {
  const s = getState();
  try {
    const automations = await listAutomationsApi(s.config);
    s.setAutomations(automations);
  } catch {
    /* leave previous list in place */
  }
}

export async function createAutomation(payload: CreateAutomationPayload): Promise<void> {
  const s = getState();
  await createAutomationApi(s.config, payload);
  await fetchAutomations();
}

export async function updateAutomation(taskId: string, patch: UpdateAutomationPayload): Promise<void> {
  const s = getState();
  await updateAutomationApi(s.config, taskId, patch);
  await fetchAutomations();
}

export async function toggleAutomation(taskId: string): Promise<void> {
  const s = getState();
  await toggleAutomationApi(s.config, taskId);
  await fetchAutomations();
}

export async function runAutomation(taskId: string): Promise<void> {
  const s = getState();
  await runAutomationApi(s.config, taskId);
  await fetchAutomations();
}

export async function deleteAutomation(taskId: string): Promise<void> {
  const s = getState();
  await deleteAutomationApi(s.config, taskId);
  await fetchAutomations();
}

export async function fetchAutomationSuggestions(): Promise<void> {
  const s = getState();
  try {
    const suggestions = await listAutomationSuggestionsApi(s.config);
    s.setAutomationSuggestions(suggestions);
  } catch {
    /* leave previous list in place */
  }
}

export async function dismissSuggestion(id: string): Promise<void> {
  const s = getState();
  s.setAutomationSuggestions((s.automationSuggestions ?? []).filter((sug) => sug.id !== id));
  await dismissAutomationSuggestionApi(s.config, id);
}

export async function refreshSuggestions(): Promise<void> {
  const s = getState();
  const suggestions = await refreshAutomationSuggestionsApi(s.config);
  s.setAutomationSuggestions(suggestions);
}
