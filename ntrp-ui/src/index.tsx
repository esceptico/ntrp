#!/usr/bin/env node
import { render } from "ink";
import App from "./App.js";
import { defaultConfig, type Config } from "./types.js";

// Check if we can run - stdin must be a TTY for raw mode
if (!process.stdin.isTTY) {
  console.error("Error: ntrp-ui requires an interactive terminal.");
  console.error("Please run in a terminal that supports raw mode.");
  process.exit(1);
}

// Parse CLI args
const args = process.argv.slice(2);
const config: Config = { ...defaultConfig };

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--server" && args[i + 1]) {
    config.serverUrl = args[++i];
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

// Render without alternate screen or mouse mode
// Uses native terminal scrollback for scrolling
const instance = render(<App config={config} />, {
  exitOnCtrlC: false,
});

// Handle unmount
instance.waitUntilExit().then(() => {
  process.exit(0);
});
