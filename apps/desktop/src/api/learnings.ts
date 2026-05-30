import type { AppConfig } from "../api";
import { apiWithConfig } from "../api";

export type LearningsAdjudicator = "dedup" | "contradiction" | "entity_link";

export interface LearningsList {
  adjudicators: LearningsAdjudicator[];
  present: LearningsAdjudicator[];
}

export interface LearningsDoc {
  adjudicator: LearningsAdjudicator;
  markdown: string;
}

export interface RecordCorrectionParams {
  action: string;
  summary: string;
  subjects?: string[];
  proposed?: string;
  correct?: string;
  reason?: string;
}

export function listLearnings(config: AppConfig) {
  return apiWithConfig<LearningsList>(config, "/admin/memory/learnings");
}

export function getLearnings(config: AppConfig, adjudicator: LearningsAdjudicator) {
  return apiWithConfig<LearningsDoc>(config, `/admin/memory/learnings/${adjudicator}`);
}

export function putLearnings(config: AppConfig, adjudicator: LearningsAdjudicator, markdown: string) {
  return apiWithConfig<LearningsDoc>(config, `/admin/memory/learnings/${adjudicator}`, {
    method: "PUT",
    body: JSON.stringify({ markdown }),
  });
}

export function recordCorrection(config: AppConfig, adjudicator: LearningsAdjudicator, params: RecordCorrectionParams) {
  return apiWithConfig<{ ok: boolean; markdown: string }>(config, `/admin/memory/learnings/${adjudicator}`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}
