import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeFileSync, readFileSync, unlinkSync, existsSync } from "node:fs";
import { PNG } from "pngjs";

export interface PixelRow {
  pixels: Array<{ fg: string; bg: string }>;
}

const PREVIEW_WIDTH = 40;

export function getImagePixels(base64: string, mediaType: string): PixelRow[] {
  const ts = Date.now();
  const ext = mediaType.includes("png") ? "png" : "jpg";
  const tmpSrc = join(tmpdir(), `ntrp-preview-${ts}.${ext}`);
  const tmpPng = join(tmpdir(), `ntrp-preview-${ts}.png`);
  try {
    writeFileSync(tmpSrc, Buffer.from(base64, "base64"));

    // Convert to tiny PNG for pixel access
    if (ext !== "png" || true) {
      spawnSync("sips", [
        "--resampleWidth", String(PREVIEW_WIDTH),
        "-s", "format", "png",
        tmpSrc, "--out", tmpPng,
      ], { stdio: "pipe" });
    }

    const pngPath = existsSync(tmpPng) ? tmpPng : tmpSrc;
    const png = PNG.sync.read(readFileSync(pngPath));
    const { width, height, data } = png;

    const hex = (i: number) =>
      `#${data[i].toString(16).padStart(2, "0")}${data[i + 1].toString(16).padStart(2, "0")}${data[i + 2].toString(16).padStart(2, "0")}`;

    const rows: PixelRow[] = [];
    for (let y = 0; y < height - 1; y += 2) {
      const pixels: PixelRow["pixels"] = [];
      for (let x = 0; x < width; x++) {
        pixels.push({
          fg: hex((y * width + x) * 4),
          bg: hex(((y + 1) * width + x) * 4),
        });
      }
      rows.push({ pixels });
    }
    return rows;
  } catch {
    return [];
  } finally {
    try { unlinkSync(tmpSrc); } catch {}
    try { unlinkSync(tmpPng); } catch {}
  }
}
