export interface LearningDetailRow {
  label: string;
  value: string;
}

export function cleanLearningText(text: string): string {
  return text.replace(/direct evidence: [^.]+/gi, "direct evidence is loaded");
}

export function summarizeLearningEvidence(evidenceIds: string[]): string {
  if (evidenceIds.length === 0) return "none";
  const counts = new Map<string, number>();
  for (const evidenceId of evidenceIds) {
    const kind = evidenceId.split(":", 1)[0] || "reference";
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([kind, count]) => `${count} ${evidenceKindLabel(kind, count)}`)
    .join(", ");
}

export function learningDetailRows(details: Record<string, unknown>): LearningDetailRow[] {
  const rows: LearningDetailRow[] = [];
  appendCleanupRule(rows, details);
  appendSourceSummary(rows, details);
  appendNumber(rows, details, "count", "matches");
  appendNumber(rows, details, "candidate_count", "profile candidates");
  appendNumber(rows, details, "issue_count", "profile issues");
  appendNumber(rows, details, "pair_count", "fact pairs");
  appendNumber(rows, details, "char_budget", "char budget");
  appendNumber(rows, details, "current_chars", "current chars");
  appendArrayCount(rows, details, "observation_ids", "matched patterns");
  appendArrayCount(rows, details, "fact_ids", "matched facts");
  appendArrayCount(rows, details, "event_ids", "source events");
  appendEvidenceSummary(rows, details);
  appendCountMap(rows, details, "outcome_counts", "outcomes");
  appendCountMap(rows, details, "scope_counts", "scopes");
  appendSampleSignal(rows, details);
  appendString(rows, details, "reason", "reason", titleCase);
  appendString(rows, details, "source", "source", titleCase);
  return rows.filter((row) => row.value.trim()).slice(0, 8);
}

function appendCleanupRule(rows: LearningDetailRow[], details: Record<string, unknown>): void {
  const criteria = objectValue(details, "criteria");
  if (!criteria) return;
  const olderThanDays = numberValue(criteria, "older_than_days");
  const maxSources = numberValue(criteria, "max_sources");
  const limit = numberValue(criteria, "limit");
  const value = [
    olderThanDays !== null ? `${olderThanDays}d old` : null,
    maxSources !== null ? `<= ${maxSources} facts` : null,
    limit !== null ? `review ${limit}` : null,
  ].filter(Boolean).join(", ");
  rows.push({ label: "cleanup rule", value });
}

function appendSourceSummary(rows: LearningDetailRow[], details: Record<string, unknown>): void {
  const summary = objectValue(details, "summary");
  if (!summary) return;
  const total = firstNumber(summary, ["total", "events", "candidates"]);
  const averageChars = numberValue(summary, "average_chars");
  const maxChars = numberValue(summary, "max_chars");
  rows.push({
    label: "source summary",
    value: [
      total !== null ? `${total} source rows` : null,
      averageChars !== null ? `${Math.round(averageChars)} avg chars` : null,
      maxChars !== null ? `${maxChars} max chars` : null,
    ].filter(Boolean).join(", ") || "loaded",
  });
}

function appendNumber(
  rows: LearningDetailRow[],
  details: Record<string, unknown>,
  key: string,
  label: string,
): void {
  const value = numberValue(details, key);
  if (value !== null) rows.push({ label, value: String(value) });
}

function appendArrayCount(
  rows: LearningDetailRow[],
  details: Record<string, unknown>,
  key: string,
  label: string,
): void {
  const value = arrayValue(details, key);
  if (value) rows.push({ label, value: String(value.length) });
}

function appendEvidenceSummary(rows: LearningDetailRow[], details: Record<string, unknown>): void {
  const evidenceIds = arrayValue(details, "direct_evidence_ids")?.filter(isString);
  if (evidenceIds?.length) rows.push({ label: "direct evidence", value: summarizeLearningEvidence(evidenceIds) });
}

function appendCountMap(
  rows: LearningDetailRow[],
  details: Record<string, unknown>,
  key: string,
  label: string,
): void {
  const value = objectValue(details, key);
  if (!value) return;
  const items = Object.entries(value)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `${name}: ${count}`);
  if (items.length) rows.push({ label, value: items.join(", ") });
}

function appendSampleSignal(rows: LearningDetailRow[], details: Record<string, unknown>): void {
  const signals = arrayValue(details, "signals")?.filter(isString);
  if (signals?.length) rows.push({ label: "sample signal", value: cleanLearningText(signals[0]) });
}

function appendString(
  rows: LearningDetailRow[],
  details: Record<string, unknown>,
  key: string,
  label: string,
  format: (value: string) => string = (value) => value,
): void {
  const value = stringValue(details, key);
  if (value) rows.push({ label, value: format(value) });
}

function evidenceKindLabel(kind: string, count: number): string {
  switch (kind) {
    case "fact":
      return count === 1 ? "fact" : "facts";
    case "observation":
      return count === 1 ? "pattern" : "patterns";
    case "memory_event":
      return count === 1 ? "memory change" : "memory changes";
    case "memory_access_event":
      return count === 1 ? "sent-memory run" : "sent-memory runs";
    case "message":
      return count === 1 ? "message" : "messages";
    case "task":
      return count === 1 ? "task" : "tasks";
    default:
      return titleCase(kind).toLowerCase();
  }
}

function titleCase(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function numberValue(details: Record<string, unknown>, key: string): number | null {
  const value = details[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function firstNumber(details: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = numberValue(details, key);
    if (value !== null) return value;
  }
  return null;
}

function stringValue(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function objectValue(details: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const value = details[key];
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function arrayValue(details: Record<string, unknown>, key: string): unknown[] | null {
  const value = details[key];
  return Array.isArray(value) ? value : null;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}
