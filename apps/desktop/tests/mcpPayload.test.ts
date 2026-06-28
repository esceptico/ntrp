import { expect, test } from "bun:test";
import { buildMCPServerPayload } from "@/features/settings/components/mcp/payload";

test("builds auto HTTP MCP payload from URL only", () => {
  expect(
    buildMCPServerPayload({
      transport: "http",
      command: "",
      argsList: [""],
      envEntries: [{ key: "", value: "" }],
      url: "https://mcp.example.com/mcp",
      headerEntries: [{ key: "Authorization", value: "Bearer stale" }],
      auth: "auto",
    }),
  ).toEqual({
    transport: "http",
    url: "https://mcp.example.com/mcp",
  });
});

test("builds header HTTP MCP payload when explicit headers are selected", () => {
  expect(
    buildMCPServerPayload({
      transport: "http",
      command: "",
      argsList: [""],
      envEntries: [{ key: "", value: "" }],
      url: "https://mcp.example.com/mcp",
      headerEntries: [{ key: "Authorization", value: "Bearer token" }],
      auth: "headers",
    }),
  ).toEqual({
    transport: "http",
    url: "https://mcp.example.com/mcp",
    headers: { Authorization: "Bearer token" },
  });
});

test("omits empty headers in explicit header mode", () => {
  expect(
    buildMCPServerPayload({
      transport: "http",
      command: "",
      argsList: [""],
      envEntries: [{ key: "", value: "" }],
      url: "https://mcp.example.com/mcp",
      headerEntries: [{ key: "", value: "" }],
      auth: "headers",
    }),
  ).toEqual({
    transport: "http",
    url: "https://mcp.example.com/mcp",
  });
});
