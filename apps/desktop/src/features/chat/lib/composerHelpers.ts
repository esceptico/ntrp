import { type ImageBlock } from "@/stores";

/** Read a single File and return its bytes as base64 + media type. */
export function fileToImageBlock(file: File): Promise<ImageBlock> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Read failed"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Unexpected reader result"));
        return;
      }
      // result is "data:<media_type>;base64,<data>"
      const [meta, data] = result.split(",", 2);
      const m = meta.match(/^data:([^;]+);base64$/);
      resolve({ media_type: m?.[1] ?? file.type ?? "application/octet-stream", data: data ?? "" });
    };
    reader.readAsDataURL(file);
  });
}

/** Returns the slash-prefix at the start of `text` if it currently looks like
 *  a command being composed (no space between the slash and the cursor). */
export function pickerQuery(text: string): string | null {
  if (!text.startsWith("/")) return null;
  // Picker stays open while the user is typing the command name (no space yet).
  const head = text.slice(1);
  if (head.includes(" ") || head.includes("\n")) return null;
  return head;
}

export function resize(input: HTMLTextAreaElement) {
  input.style.height = "0px";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
}
