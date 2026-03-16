import { PNG } from "pngjs";

const UPPER_HALF = "▀";

export function renderImagePreview(base64: string, maxWidth = 40): string {
  const buf = Buffer.from(base64, "base64");
  const png = PNG.sync.read(buf);
  const { width, height, data } = png;

  const scale = Math.min(maxWidth / width, 1);
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);

  const sample = (x: number, y: number): [number, number, number] => {
    const sx = Math.min(Math.floor(x / scale), width - 1);
    const sy = Math.min(Math.floor(y / scale), height - 1);
    const i = (sy * width + sx) * 4;
    return [data[i], data[i + 1], data[i + 2]];
  };

  const lines: string[] = [];
  for (let y = 0; y < h - 1; y += 2) {
    let line = "";
    for (let x = 0; x < w; x++) {
      const [tr, tg, tb] = sample(x, y);
      const [br, bg, bb] = sample(x, y + 1);
      line += `\x1b[38;2;${tr};${tg};${tb};48;2;${br};${bg};${bb}m${UPPER_HALF}`;
    }
    lines.push(line + "\x1b[0m");
  }
  return lines.join("\n");
}
