import { PNG } from "pngjs";

interface PixelRow {
  pixels: Array<{ fg: string; bg: string }>;
}

export function getImagePixels(base64: string, maxWidth = 40): PixelRow[] {
  const buf = Buffer.from(base64, "base64");
  const png = PNG.sync.read(buf);
  const { width, height, data } = png;

  const scale = Math.min(maxWidth / width, 1);
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);

  const sample = (x: number, y: number): string => {
    const sx = Math.min(Math.floor(x / scale), width - 1);
    const sy = Math.min(Math.floor(y / scale), height - 1);
    const i = (sy * width + sx) * 4;
    return `#${data[i].toString(16).padStart(2, "0")}${data[i + 1].toString(16).padStart(2, "0")}${data[i + 2].toString(16).padStart(2, "0")}`;
  };

  const rows: PixelRow[] = [];
  for (let y = 0; y < h - 1; y += 2) {
    const pixels: PixelRow["pixels"] = [];
    for (let x = 0; x < w; x++) {
      pixels.push({ fg: sample(x, y), bg: sample(x, y + 1) });
    }
    rows.push({ pixels });
  }
  return rows;
}
