export interface MemoryTarget<T> {
  item: T;
  nonce: number;
}

export function nextMemoryTarget<T>(previous: MemoryTarget<T> | null, item: T): MemoryTarget<T> {
  return {
    item,
    nonce: (previous?.nonce ?? 0) + 1,
  };
}

export function memoryTargetId<T extends { id: number }>(
  target: MemoryTarget<T | number> | null | undefined,
): number | null {
  if (!target) return null;
  return typeof target.item === "number" ? target.item : target.item.id;
}

export function memoryTargetItem<T>(itemsById: Map<number, T>, id: number): T | number {
  return itemsById.get(id) ?? id;
}

export function selectedMemoryItem<T extends { id: number }>(
  items: T[] | null | undefined,
  selectedId: number | null,
  detailItem?: T | null,
): T | null {
  if (selectedId === null) return null;
  if (detailItem?.id === selectedId) return detailItem;
  return items?.find((item) => item.id === selectedId) ?? null;
}

export function upsertById<T extends { id: number }>(items: T[] | null | undefined, item: T): T[] {
  const existing = items ?? [];
  return [item, ...existing.filter((candidate) => candidate.id !== item.id)];
}
