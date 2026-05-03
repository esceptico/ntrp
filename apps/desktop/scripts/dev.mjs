import { spawn } from "node:child_process";

const devUrl = "http://127.0.0.1:5175";
const children = new Set();

function run(command, args, options = {}) {
  const child = spawn(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options,
  });
  children.add(child);
  child.on("exit", () => children.delete(child));
  return child;
}

async function waitForVite() {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(devUrl);
      if (response.ok) return;
    } catch {
      await new Promise(resolve => setTimeout(resolve, 150));
    }
  }
  throw new Error(`Vite did not start at ${devUrl}`);
}

function shutdown(code = 0) {
  for (const child of children) child.kill();
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

const vite = run("vite", ["--host", "127.0.0.1", "--port", "5175", "--strictPort"]);

try {
  await waitForVite();
} catch (error) {
  console.error(error);
  shutdown(1);
}

const electron = run("electron", ["."], {
  env: {
    ...process.env,
    NTRP_DESKTOP_DEV_SERVER_URL: devUrl,
  },
});

electron.on("exit", code => shutdown(code ?? 0));
vite.on("exit", code => {
  if (code !== 0) shutdown(code ?? 1);
});
