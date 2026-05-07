const RECALL_REASON_LABELS: Record<string, string> = {
  fact_match: "Fact matched query",
  pattern_match: "Pattern matched query",
  shared_entity: "Shared entity",
  source_fact_match: "Source fact matched query",
  temporal_neighbor: "Temporal neighbor",
};

export function memoryRecallReasonLabel(reason: string): string {
  return RECALL_REASON_LABELS[reason] ?? reason;
}
