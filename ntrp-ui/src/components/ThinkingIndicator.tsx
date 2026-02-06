import React, { useState, useEffect, useRef, useMemo } from "react";
import { Text } from "ink";
import { colors } from "./ui/colors.js";
import { useAccentColor } from "../hooks/index.js";

const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const GLIMMER_WIDTH = 3;
const VERBS = ["thinking", "processing", "analyzing", "reasoning", "considering", "pondering"];

function pickVerb() {
  return VERBS[Math.floor(Math.random() * VERBS.length)];
}

interface ThinkingIndicatorProps {
  status: string;
}

export function ThinkingIndicator({ status }: ThinkingIndicatorProps) {
  const { accentValue } = useAccentColor();
  const [frame, setFrame] = useState(0);
  const [verb, setVerb] = useState(pickVerb);
  const prevStatus = useRef(status);

  useEffect(() => {
    if (status !== prevStatus.current && (status === "thinking..." || status === "")) {
      setVerb(pickVerb());
    }
    prevStatus.current = status;
  }, [status]);

  useEffect(() => {
    const interval = setInterval(() => setFrame(f => f + 1), 100);
    return () => clearInterval(interval);
  }, []);

  const displayText = `${verb}...`;
  const glimmerPos = frame % (displayText.length + GLIMMER_WIDTH);

  // Single Text element with nested Text for inline color changes
  const shimmerText = useMemo(() => {
    return displayText.split("").map((char, i) => {
      const dist = Math.abs(i - glimmerPos);
      const isHighlight = dist < GLIMMER_WIDTH;
      return (
        <Text key={i} color={isHighlight ? colors.status.processingShimmer : accentValue}>
          {char}
        </Text>
      );
    });
  }, [displayText, glimmerPos]);

  return (
    <Text>
      <Text color={accentValue}>{SPINNER[frame % SPINNER.length]} </Text>
      {shimmerText}
      <Text color={colors.text.muted}> (Esc to cancel)</Text>
    </Text>
  );
}
