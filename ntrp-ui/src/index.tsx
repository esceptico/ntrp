#!/usr/bin/env bun
import { createCliRenderer } from "@opentui/core";
import { createRoot } from "@opentui/react";
import App from "./App.js";
import { setApiKey } from "./api/fetch.js";
import { checkHealth } from "./api/client.js";
import { getCredentials } from "./lib/secrets.js";
import type { Config } from "./types.js";

// Parse CLI args
const args = process.argv.slice(2);
let cliServer: string | undefined;
let cliToken: string | undefined;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--server" && args[i + 1]) {
    cliServer = args[++i]!;
  } else if (args[i] === "--token" && args[i + 1]) {
    cliToken = args[++i]!;
  } else if (args[i] === "--version" || args[i] === "-v") {
    const pkg = await import("../package.json");
    console.log(pkg.version);
    process.exit(0);
  } else if (args[i] === "--help" || args[i] === "-h") {
    console.log(`
ntrp - Personal entropy reduction system

Usage:
  ntrp [options]

Options:
  --server URL     Server URL (default: http://localhost:8000)
  --token TOKEN    API key for server authentication (or set NTRP_API_KEY)
  --version, -v    Show version
  --help, -h       Show this help
`);
    process.exit(0);
  }
}

// Config resolution: CLI > env > keychain > defaults
const envServer = process.env.NTRP_SERVER_URL;
const envToken = process.env.NTRP_API_KEY;
const saved = await getCredentials();

const serverUrl = cliServer || envServer || saved.serverUrl || "http://localhost:8000";
const apiKey = cliToken || envToken || saved.apiKey || "";
let needsSetup = !apiKey;
let needsProvider = false;

// Verify saved credentials — only invalidate if server is reachable but auth fails
if (apiKey && !cliToken && !envToken) {
  setApiKey(apiKey);
  const health = await checkHealth({ serverUrl, apiKey, needsSetup: false });
  if (!health.ok && health.version !== null) needsSetup = true;
  if (health.ok && !health.hasProviders) needsProvider = true;
}

const config: Config = { serverUrl, apiKey, needsSetup, needsProvider };

if (apiKey) setApiKey(apiKey);

const renderer = await createCliRenderer({
  exitOnCtrlC: false,
});

createRoot(renderer).render(<App config={config} />);
