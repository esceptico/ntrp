import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readFileSync, unlinkSync, existsSync } from "node:fs";
import type { ImageBlock } from "../api/chat.js";

const MAX_DIMENSION = 1568;

const OSASCRIPT = [
  "osascript",
  "-e", 'set imageData to the clipboard as "PNGf"',
  "-e", `set fileRef to open for access POSIX file "__TMP__" with write permission`,
  "-e", "set eof fileRef to 0",
  "-e", "write imageData to fileRef",
  "-e", "close access fileRef",
];

export function getClipboardImage(): ImageBlock | null {
  if (process.platform !== "darwin") return null;

  const ts = Date.now();
  const tmpPng = join(tmpdir(), `ntrp-clip-${ts}.png`);
  const tmpJpg = join(tmpdir(), `ntrp-clip-${ts}.jpg`);
  try {
    const args = OSASCRIPT.map((a) => a.replace("__TMP__", tmpPng));
    spawnSync(args[0], args.slice(1), { stdio: "pipe" });
    if (!existsSync(tmpPng) || readFileSync(tmpPng).length === 0) return null;

    spawnSync("sips", [
      "--resampleHeightWidthMax", String(MAX_DIMENSION),
      "--setProperty", "formatOptions", "80",
      "-s", "format", "jpeg",
      tmpPng, "--out", tmpJpg,
    ], { stdio: "pipe" });

    if (!existsSync(tmpJpg)) return null;
    const buf = readFileSync(tmpJpg);
    if (buf.length === 0) return null;

    return { media_type: "image/jpeg", data: buf.toString("base64") };
  } catch {
    return null;
  } finally {
    try { unlinkSync(tmpPng); } catch {}
    try { unlinkSync(tmpJpg); } catch {}
  }
}
