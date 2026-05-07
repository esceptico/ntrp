export interface CustomModelDraft {
  model_id: string;
  base_url: string;
  context_window: number;
  max_output_tokens: number;
  api_key: string;
}

export function defaultCustomModelDraft(): CustomModelDraft {
  return {
    model_id: "",
    base_url: "",
    context_window: 8192,
    max_output_tokens: 8192,
    api_key: "",
  };
}

export function canSaveCustomModelDraft(draft: CustomModelDraft): boolean {
  return (
    draft.model_id.trim().length > 0 &&
    draft.base_url.trim().length > 0 &&
    draft.context_window > 0 &&
    draft.max_output_tokens > 0
  );
}
