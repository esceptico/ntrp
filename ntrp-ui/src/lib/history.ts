import type { Message } from "../types.js";
import type { HistoryMessage } from "../api/sessions.js";
import { truncateText } from "./utils.js";
import { MAX_TOOL_MESSAGE_CHARS, MAX_TOOL_DESCRIPTION_CHARS } from "./constants.js";

function extractDescription(name: string, argsJson?: string): string | undefined {
  if (!argsJson) return undefined;
  try {
    const args = JSON.parse(argsJson);
    switch (name) {
      case "bash":
        return args.command;
      case "read_note":
      case "read_file":
      case "view":
        return args.path || args.file_path;
      case "edit_note":
      case "create_note":
        return args.path;
      case "search":
        return args.query;
      case "web_search":
        return args.query;
      case "delegate":
      case "explore":
        return args.task || args.description;
      default:
        return undefined;
    }
  } catch {
    return undefined;
  }
}

export function convertHistoryToMessages(raw: HistoryMessage[]): Message[] {
  const messages: Message[] = [];

  // Build lookup: tool_call_id → { name, description }
  const toolMeta = new Map<string, { name: string; description?: string }>();
  for (const msg of raw) {
    if (msg.role === "assistant" && msg.tool_calls) {
      for (const tc of msg.tool_calls) {
        const description = extractDescription(tc.name, tc.arguments);
        toolMeta.set(tc.id, { name: tc.name, description });
      }
    }
  }

  let idCounter = 0;
  for (const msg of raw) {
    switch (msg.role) {
      case "user":
        messages.push({
          id: `h-${idCounter++}`,
          role: "user",
          content: msg.content,
          images: msg.images,
          imageCount: msg.images?.length,
        });
        break;

      case "assistant":
        if (msg.content?.trim()) {
          messages.push({ id: `h-${idCounter++}`, role: "assistant", content: msg.content });
        }
        break;

      case "tool": {
        if (!msg.tool_call_id) break;
        const meta = toolMeta.get(msg.tool_call_id);
        const toolName = meta?.name || "tool";
        const toolDescription = meta?.description
          ? truncateText(meta.description, MAX_TOOL_DESCRIPTION_CHARS, "end")
          : undefined;
        const content = truncateText(msg.content, MAX_TOOL_MESSAGE_CHARS, "end");
        messages.push({
          id: `h-${idCounter++}`,
          role: "tool",
          content,
          toolName,
          toolDescription,
        });
        break;
      }
    }
  }

  return messages;
}
