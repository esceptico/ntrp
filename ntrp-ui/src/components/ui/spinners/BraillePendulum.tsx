import { useState, useEffect, useMemo } from "react";

const dotBits = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
];

function generateFrames(width: number, maxSpread: number): string[] {
  const totalFrames = 120;
  const pixelCols = width * 2;
  const frames: string[] = [];

  for (let t = 0; t < totalFrames; t++) {
    const codes: number[] = Array.from({ length: width }, () => 0x2800);
    const progress = t / totalFrames;
    const spread = Math.sin(Math.PI * progress) * maxSpread;
    const basePhase = progress * Math.PI * 8;

    for (let pc = 0; pc < pixelCols; pc++) {
      const swing = Math.sin(basePhase + pc * spread);
      const center = (1 - swing) * 1.5;

      for (let row = 0; row < 4; row++) {
        if (Math.abs(row - center) < 0.7) {
          const charIdx = Math.floor(pc / 2);
          const dc = pc % 2;
          codes[charIdx]! |= dotBits[row]![dc]!;
        }
      }
    }

    frames.push(codes.map(c => String.fromCharCode(c)).join(""));
  }

  return frames;
}

interface BraillePendulumProps {
  width?: number;
  interval?: number;
  color?: string;
  spread?: number;
}

export function BraillePendulum({
  width = 10,
  interval = 40,
  color,
  spread = 0.5,
}: BraillePendulumProps) {
  const frames = useMemo(() => generateFrames(width, spread), [width, spread]);
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame(prev => (prev + 1) % frames.length);
    }, interval);
    return () => clearInterval(timer);
  }, [interval, frames.length]);

  return <text><span fg={color}>{frames[frame]}</span></text>;
}
