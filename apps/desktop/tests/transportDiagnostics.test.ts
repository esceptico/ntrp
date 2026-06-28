import { expect, test } from "bun:test";
import { formatTransportDiagnostics } from "@/lib/transportDiagnostics";

test("formats transport diagnostics for the chat header surface", () => {
  const formatted = formatTransportDiagnostics({
    connectionPhase: "reconnecting",
    lastSeq: 7,
    lastKeepaliveSeq: 9,
    connectAfterSeq: 7,
    lastClosedReason: "eof",
    lastError: null,
    updatedAt: 123,
  });

  expect(formatted.label).toBe("reconnecting · seq 7 · keepalive 9");
  expect(formatted.title).toContain("phase: reconnecting");
  expect(formatted.title).toContain("after_seq: 7");
  expect(formatted.title).toContain("last close: eof");
});
