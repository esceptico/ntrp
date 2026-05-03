import { useState, useEffect } from "react";
import { Panel } from "../layout/Panel.js";
import { colors } from "../colors.js";

interface LoadingProps {
  message?: string;
}

const SPINNER_FRAMES = ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827", "\u2807", "\u280F"];

export function Loading({ message = "Loading..." }: LoadingProps) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame((f) => (f + 1) % SPINNER_FRAMES.length);
    }, 80);
    return () => clearInterval(interval);
  }, []);

  return (
    <Panel>
      <text>
        <span fg={colors.status.processing}>{SPINNER_FRAMES[frame]}</span>
        {" "}
        <span fg={colors.text.secondary}>{message}</span>
      </text>
    </Panel>
  );
}
