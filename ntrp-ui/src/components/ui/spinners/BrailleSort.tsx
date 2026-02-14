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
  const pixelCols = width * 2;
  const totalFrames = 100;
  const frames: string[] = [];

  const rand = seededRandom(19);
  const shuffled: number[] = [];
  for (let i = 0; i < pixelCols; i++) {
    shuffled.push(rand() * 3);
  }

  const target: number[] = [];
  for (let i = 0; i < pixelCols; i++) {
    target.push((i / (pixelCols - 1)) * 3);
  }

  for (let t = 0; t < totalFrames; t++) {
    const codes: number[] = Array.from({ length: width }, () => 0x2800);
    const progress = t / totalFrames;
    const cursor = progress * pixelCols * 1.2;

    for (let pc = 0; pc < pixelCols; pc++) {
      const charIdx = Math.floor(pc / 2);
      const dc = pc % 2;
      let center: number;

      const distFromCursor = pc - cursor;

      if (distFromCursor < -3) {
        center = target[pc]!;
      } else if (distFromCursor < 2) {
        const blend = 1 - (distFromCursor + 3) / 5;
        const ease = blend * blend * (3 - 2 * blend);
        center = shuffled[pc]! + (target[pc]! - shuffled[pc]!) * ease;

        if (Math.abs(distFromCursor) < 0.8) {
          for (let row = 0; row < 4; row++) {
            codes[charIdx]! |= dotBits[row]![dc]!;
          }
          continue;
        }
      } else {
        const jitter = Math.sin(progress * Math.PI * 16 + pc * 2.7) * 0.6
          + Math.sin(progress * Math.PI * 9 + pc * 1.3) * 0.4;
        center = shuffled[pc]! + jitter;
      }

      center = Math.max(0, Math.min(3, center));

      for (let row = 0; row < 4; row++) {
        if (Math.abs(row - center) < 0.7) {
          codes[charIdx]! |= dotBits[row]![dc]!;
        }
      }
    }

    frames.push(codes.map(c => String.fromCharCode(c)).join(""));
  }

  return frames;
}

interface BrailleSortProps {
  width?: number;
  interval?: number;
  color?: string;
}

export function BrailleSort({
  width = 10,
  interval = 40,
  color,
}: BrailleSortProps) {
  const frames = useMemo(() => generateFrames(width), [width]);
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame(prev => (prev + 1) % frames.length);
    }, interval);
    return () => clearInterval(timer);
  }, [interval, frames.length]);

  return <text><span fg={color}>{frames[frame]}</span></text>;
}
