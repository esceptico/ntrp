#!/usr/bin/env bun
import { createCliRenderer } from "@opentui/core";
import { createRoot } from "@opentui/react";
import App from "./App.js";
import { defaultConfig, type Config } from "./types.js";

// Parse CLI args
const args = process.argv.slice(2);
const config: Config = { ...defaultConfig };

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--server" && args[i + 1]) {
    config.serverUrl = args[++i]!;
  } else if (args[i] === "--help" || args[i] === "-h") {
    console.log(`
ntrp - Personal entropy reduction system

Usage:
  ntrp-ui [options]

Options:
  --server URL     Server URL (default: http://localhost:8000)
  --help, -h       Show this help
`);
    process.exit(0);
  }
}

const renderer = await createCliRenderer({
  exitOnCtrlC: false,
});

createRoot(renderer).render(<App config={config} />);
