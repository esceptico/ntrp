/**
 * Incremental Server-Sent Events frame parser, shared by the two transports
 * that read the chat stream so they parse the wire format identically:
 *   - the Electron main-process reader (electron/main.cjs, via dynamic import)
 *   - the renderer fetch fallback (src/hooks/useEvents.ts)
 *
 * ESM so Vite/Rollup bundle it straight into the renderer and bun imports it in
 * tests; the CommonJS main process loads it with `await import()`. Pure — no
 * Node or DOM dependencies. Each caller owns its own byte reader + TextDecoder
 * and feeds decoded text chunks in; `data:` frames may span chunk boundaries,
 * hence the carried `buffer`.
 */
export function createSseFrameParser() {
  let buffer = "";
  return {
    /**
     * Feed a decoded text chunk. Returns the JSON-parsed payloads of any
     * `data:` frames that completed in this chunk (in order). Non-JSON lines
     * (SSE keepalive comments, blank separators) are skipped.
     * @param {string} chunk
     * @returns {unknown[]}
     */
    push(chunk) {
      buffer += chunk;
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      const events = [];
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          events.push(JSON.parse(line.slice(6)));
        } catch {
          // keepalive / non-data line — ignore
        }
      }
      return events;
    },
  };
}
