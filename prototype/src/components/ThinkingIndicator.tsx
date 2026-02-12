import { useState, useEffect, useRef, useMemo } from "react";
import { colors } from "./ui/colors.js";
import { useAccentColor } from "../hooks/index.js";

const GLIMMER_WIDTH = 3;
const SPINNER_FRAMES = ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827", "\u2807", "\u280F"];
const VERBS = ["thinking", "processing", "analyzing", "reasoning", "considering", "pondering"] as const;

function pickVerb() {
  return VERBS[Math.floor(Math.random() * VERBS.length)];
}

interface ThinkingIndicatorProps {
  status: string;
}

export function ThinkingIndicator({ status }: ThinkingIndicatorProps) {
  const { accentValue } = useAccentColor();
  const [tick, setTick] = useState(0);
  const [verb, setVerb] = useState(pickVerb);
  const prevStatus = useRef(status);

  useEffect(() => {
    if (status !== prevStatus.current && (status === "thinking..." || status === "")) {
      setVerb(pickVerb());
    }
    prevStatus.current = status;
  }, [status]);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 100);
    return () => clearInterval(interval);
  }, []);

  const spinnerFrame = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
  const isGenericStatus = !status || status === "thinking..." || status === "";
  const displayText = isGenericStatus ? `${verb}...` : status;
  const glimmerPos = tick % (displayText.length + GLIMMER_WIDTH);

  const shimmerChars = useMemo(() => {
    return displayText.split("").map((char, i) => {
      const dist = Math.abs(i - glimmerPos);
      const isHighlight = dist < GLIMMER_WIDTH;
      return { char, color: isHighlight ? colors.status.processingShimmer : accentValue };
    });
  }, [displayText, glimmerPos, accentValue]);

  return (
    <text>
      <span fg={accentValue}>{spinnerFrame} </span>
      {shimmerChars.map((s, i) => (
        <span key={i} fg={s.color}>{s.char}</span>
      ))}
      <span fg={colors.text.muted}> (Esc to cancel)</span>
    </text>
  );
}
