import React from "react";
import { Text } from "ink";

const BLOCKS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588";

interface SparklineProps {
  data: number[];
  width: number;
  color?: string;
}

export function Sparkline({ data, width, color }: SparklineProps) {
  const max = Math.max(...data, 1);
  const chars = data.slice(-width).map((v) => {
    const idx = Math.round((v / max) * (BLOCKS.length - 1));
    return BLOCKS[idx];
  });
  return <Text color={color}>{chars.join("")}</Text>;
}
