export function memoryAccessSourceLabel(source: string): string {
  if (source === "chat_prompt") return "chat prompt";
  if (source === "operator_prompt") return "automation prompt";
  if (source === "recall_tool") return "recall tool";
  return source;
}
