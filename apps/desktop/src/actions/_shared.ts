import { getState } from "@/store";

export function truncatePrompt(prompt: string, max = 80): string {
  const single = prompt.replace(/\s+/g, " ").trim();
  return single.length > max ? single.slice(0, max - 1) + "…" : single;
}

export function formatCall(name: string, argsJson: string): string {
  try {
    const parsed = JSON.parse(argsJson || "{}");
    if (parsed && typeof parsed === "object") {
      const entries = Object.entries(parsed as Record<string, unknown>);
      if (entries.length === 0) return `${name}()`;
      const parts = entries.map(([k, v]) => {
        const val = typeof v === "string" ? `"${v}"` : JSON.stringify(v);
        return `${k}=${val}`;
      });
      const full = `${name}(${parts.join(", ")})`;
      return full.length > 120 ? `${full.slice(0, 117)}…` : full;
    }
  } catch {
    /* fall through */
  }
  return name;
}

export function appendStatus(content: string): void {
  getState().appendMessage({
    id: crypto.randomUUID(),
    role: "status",
    content,
  });
}

export function appendError(content: string): void {
  getState().appendMessage({
    id: crypto.randomUUID(),
    role: "error",
    content,
  });
}

export function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

export function formatCost(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}
