import { beforeEach, expect, test } from "bun:test";
import {
  handleServerEvent,
  resetEventSeqStateForTest,
  resetReplayGapReloadStateForTest,
  resetStreamStateForTest,
} from "../src/hooks/useEvents.js";
import { historyMessagesToUi } from "../src/actions/history.ts";
import { resolutionFromResult } from "../src/lib/htmlWidget.ts";
import { activityItemStatus } from "../src/lib/agent.ts";
import { getState, setState, type ActivityItem } from "../src/store/index.js";
import type { HistoryMessage } from "../src/api.js";

const WIDGET_ARGS = JSON.stringify({
  html: "<form>pick</form>",
  title: "Pick a time slot",
  mode: "input",
});
const ACCEPT_ENVELOPE = '{"action": "accept", "values": {"rating": 4}}';

beforeEach(() => {
  resetStreamStateForTest();
  resetEventSeqStateForTest();
  resetReplayGapReloadStateForTest();
  setState({
    currentSessionId: "sess-1",
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
    error: null,
  });
});

function findActivityItem(id: string): ActivityItem | undefined {
  for (const message of getState().messages.values()) {
    const found = message.activity?.items.find((it) => it.id === id);
    if (found) return found;
  }
  return undefined;
}

test("input_needed lifts the render_html call into a pending html widget", () => {
  handleServerEvent({ type: "RUN_STARTED", session_id: "sess-1", run_id: "run-1", seq: 1 });
  handleServerEvent({
    type: "TOOL_CALL_START",
    session_id: "sess-1",
    tool_call_id: "t1",
    tool_call_name: "render_html",
    kind: "html_widget",
    seq: 2,
  });
  handleServerEvent({
    type: "TOOL_CALL_ARGS",
    session_id: "sess-1",
    tool_call_id: "t1",
    delta: WIDGET_ARGS,
    seq: 3,
  });
  handleServerEvent({ type: "TOOL_CALL_END", session_id: "sess-1", tool_call_id: "t1", seq: 4 });
  handleServerEvent({
    type: "input_needed",
    session_id: "sess-1",
    tool_id: "t1",
    name: "render_html",
    title: "Pick a time slot",
    html: "<form>pick</form>",
    seq: 5,
  });

  const item = findActivityItem("t1");
  expect(item).toBeTruthy();
  expect(item!.semanticKind).toBe("html_widget");
  expect(item!.htmlWidget).toEqual({
    html: "<form>pick</form>",
    title: "Pick a time slot",
    mode: "input",
  });
  expect(activityItemStatus(item!)).toBe("ongoing");

  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    session_id: "sess-1",
    tool_call_id: "t1",
    name: "render_html",
    kind: "html_widget",
    content: ACCEPT_ENVELOPE,
    preview: "Pick a time slot",
    data: { html: "<form>pick</form>", title: "Pick a time slot", mode: "input" },
    seq: 6,
  });

  const resolved = findActivityItem("t1");
  expect(resolved!.result).toBe(ACCEPT_ENVELOPE);
  expect(activityItemStatus(resolved!)).toBe("executed");
  expect(resolved!.htmlWidget?.mode).toBe("input");
});

test("display-mode TOOL_CALL_RESULT carries the widget payload via data", () => {
  handleServerEvent({ type: "RUN_STARTED", session_id: "sess-1", run_id: "run-1", seq: 1 });
  handleServerEvent({
    type: "TOOL_CALL_START",
    session_id: "sess-1",
    tool_call_id: "t2",
    tool_call_name: "render_html",
    kind: "html_widget",
    seq: 2,
  });
  handleServerEvent({ type: "TOOL_CALL_END", session_id: "sess-1", tool_call_id: "t2", seq: 3 });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    session_id: "sess-1",
    tool_call_id: "t2",
    name: "render_html",
    kind: "html_widget",
    content: 'Rendered HTML widget "Quarterly burn".',
    preview: "Quarterly burn",
    data: { html: "<div>chart</div>", title: "Quarterly burn", mode: "display" },
    seq: 4,
  });

  const item = findActivityItem("t2");
  expect(item!.htmlWidget).toEqual({
    html: "<div>chart</div>",
    title: "Quarterly burn",
    mode: "display",
  });
});

test("history rebuild derives the widget from tool-call args and the envelope from the result", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "pick a slot", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-1",
      tool_calls: [
        { id: "t1", name: "render_html", kind: "html_widget", arguments: WIDGET_ARGS },
      ],
    },
    { role: "tool", content: ACCEPT_ENVELOPE, id: "tool-result-1", tool_call_id: "t1" },
  ];

  const items = historyMessagesToUi(messages, null);
  const activity = items.find((it) => it.role === "activity");
  const item = activity?.activity?.items.find((it) => it.id === "t1");

  expect(item).toBeTruthy();
  expect(item!.semanticKind).toBe("html_widget");
  expect(item!.htmlWidget).toEqual({
    html: "<form>pick</form>",
    title: "Pick a time slot",
    mode: "input",
  });
  expect(resolutionFromResult(item!.result)?.action).toBe("accept");
});

test("history rebuild leaves errored input-mode calls as plain rows (no live-looking widget)", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "pick a slot", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-1",
      tool_calls: [
        { id: "t1", name: "render_html", kind: "html_widget", arguments: WIDGET_ARGS },
      ],
    },
    {
      role: "tool",
      content:
        'No interactive client connected — render_html mode="input" requires an active desktop session.',
      id: "tool-result-1",
      tool_call_id: "t1",
    },
  ];

  const items = historyMessagesToUi(messages, null);
  const activity = items.find((it) => it.role === "activity");
  const item = activity?.activity?.items.find((it) => it.id === "t1");

  expect(item).toBeTruthy();
  expect(item!.htmlWidget).toBeUndefined();
});
