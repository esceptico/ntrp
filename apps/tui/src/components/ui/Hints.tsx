import React from "react";
import { colors } from "./colors.js";

type HintPair = [key: string, action: string];

interface HintsProps {
  items: HintPair[];
}

export function Hints({ items }: HintsProps) {
  return (
    <text>
      {items.map(([key, action], i) => (
        <React.Fragment key={i}>
          {i > 0 && "  "}
          <span fg={colors.footer}>{key}</span>
          <span fg={colors.text.disabled}>{" "}{action}</span>
        </React.Fragment>
      ))}
    </text>
  );
}
