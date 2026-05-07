import { expect, test } from "bun:test";
import {
  gmailAccountSummary,
  serviceConnectionLabel,
  serviceActionLabel,
} from "../src/lib/integrationConnection.js";

test("summarizes Google accounts without exposing token filenames", () => {
  const accounts = [
    { email: "one@example.com", token_file: "gmail_token_one@example.com.json", has_send_scope: true },
    { email: "two@example.com", token_file: "gmail_token_two@example.com.json", has_send_scope: false },
  ];

  expect(gmailAccountSummary(accounts)).toBe("2 accounts");
});

test("labels env-managed service tokens as read-only", () => {
  const service = {
    id: "slack_bot_token",
    name: "Slack bot token",
    connected: true,
    from_env: true,
    key_hint: "xoxb-...abcd",
  };

  expect(serviceConnectionLabel(service)).toBe("Connected via env");
  expect(serviceActionLabel(service)).toBe("Env-managed");
});
