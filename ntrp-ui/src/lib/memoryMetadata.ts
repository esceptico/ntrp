export interface MemoryMetadataRow {
  label: string;
  value: string;
}

const HIDDEN_KEYS = new Set(["source_event_id"]);

export function memoryMetadataRows(details: Record<string, unknown>, limit = 8): MemoryMetadataRow[] {
  const rows: MemoryMetadataRow[] = [];
  for (const [key, value] of Object.entries(details)) {
    if (HIDDEN_KEYS.has(key)) continue;
    const row = metadataRow(key, value);
    if (row) rows.push(row);
    if (rows.length >= limit) break;
  }
  return rows;
}

function metadataRow(key: string, value: unknown): MemoryMetadataRow | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    return { label: labelForKey(key), value: `${value.length} ${itemLabel(key, value.length)}` };
  }
  if (typeof value === "object") {
    const size = Object.keys(value as Record<string, unknown>).length;
    return { label: labelForKey(key), value: size ? `${size} fields loaded` : "loaded" };
  }
  if (typeof value === "boolean") {
    return { label: labelForKey(key), value: value ? "yes" : "no" };
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return { label: labelForKey(key), value: String(value) };
  }
  if (typeof value === "string" && value.trim()) {
    return { label: labelForKey(key), value };
  }
  return null;
}

function itemLabel(key: string, count: number): string {
  if (key.endsWith("_ids")) return count === 1 ? "record" : "records";
  if (key.endsWith("s")) return key.replace(/_/g, " ");
  return count === 1 ? "item" : "items";
}

function labelForKey(key: string): string {
  return key
    .replace(/_ids$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}
