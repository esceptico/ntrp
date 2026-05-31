import { expect, test } from "bun:test";
import { createSseFrameParser } from "../electron/sse-frame-parser.js";

test("parses complete data frames in order", () => {
  const p = createSseFrameParser();
  expect(p.push('data: {"a":1}\ndata: {"b":2}\n')).toEqual([{ a: 1 }, { b: 2 }]);
});

test("buffers a frame split across chunk boundaries", () => {
  const p = createSseFrameParser();
  expect(p.push('data: {"a":')).toEqual([]); // incomplete line held in buffer
  expect(p.push("1}\n")).toEqual([{ a: 1 }]);
});

test("skips keepalive comments and non-JSON data lines", () => {
  const p = createSseFrameParser();
  expect(p.push(": keepalive\n\nevent: x\ndata: not json\ndata: {\"ok\":true}\n")).toEqual([
    { ok: true },
  ]);
});
