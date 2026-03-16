import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readFileSync, unlinkSync, existsSync } from "node:fs";
import type { ImageBlock } from "../api/chat.js";

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

  const tmpPath = join(tmpdir(), `ntrp-clip-${Date.now()}.png`);
  try {
    const args = OSASCRIPT.map((a) => a.replace("__TMP__", tmpPath));
    spawnSync(args[0], args.slice(1), { stdio: "pipe" });

    if (!existsSync(tmpPath)) return null;

    const buf = readFileSync(tmpPath);
    if (buf.length === 0) return null;

    return { media_type: "image/png", data: buf.toString("base64") };
  } catch {
    return null;
  } finally {
    try { unlinkSync(tmpPath); } catch {}
  }
}
