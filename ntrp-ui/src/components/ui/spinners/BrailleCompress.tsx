import { useState, useEffect, useMemo } from "react";

const dotBits = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
];

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

function generateFrames(width: number): string[] {
  const totalFrames = 100;
  const pixelCols = width * 2;
  const totalDots = pixelCols * 4;
  const frames: string[] = [];

  const rand = seededRandom(42);
  const importance: number[] = [];
  for (let i = 0; i < totalDots; i++) {
    importance.push(rand());
  }

  for (let t = 0; t < totalFrames; t++) {
    const codes: number[] = Array.from({ length: width }, () => 0x2800);
    const progress = t / totalFrames;

    const sieveThreshold = Math.max(0.1, 1 - progress * 1.2);

    const squeeze = Math.min(1, progress / 0.85);
    const activeWidth = Math.max(1, pixelCols * (1 - squeeze * 0.95));

    for (let pc = 0; pc < pixelCols; pc++) {
      const mappedPc = (pc / pixelCols) * activeWidth;
      if (mappedPc >= activeWidth) continue;

      const targetPc = Math.round(mappedPc);
      if (targetPc >= pixelCols) continue;

      const charIdx = Math.floor(targetPc / 2);
      const dc = targetPc % 2;

      for (let row = 0; row < 4; row++) {
        const dotIdx = pc * 4 + row;
        if (importance[dotIdx]! < sieveThreshold) {
          codes[charIdx]! |= dotBits[row]![dc]!;
        }
      }
    }

    frames.push(codes.map((c) => String.fromCharCode(c)).join(""));
  }

  return frames;
}

interface BrailleCompressProps {
  width?: number;
  interval?: number;
  color?: string;
}

export function BrailleCompress({
  width = 10,
  interval = 40,
  color,
}: BrailleCompressProps) {
  const frames = useMemo(() => generateFrames(width), [width]);
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame((prev) => (prev + 1) % frames.length);
    }, interval);
    return () => clearInterval(timer);
  }, [interval, frames.length]);

  return <text><span fg={color}>{frames[frame]}</span></text>;
}
