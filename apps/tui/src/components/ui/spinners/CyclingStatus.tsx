import { useState, useEffect } from "react";
import { colors } from "../colors.js";
import { Status, type Status as StatusType } from "../../../lib/constants.js";

const VERBS = [
  "thinking",
  "reasoning",
  "analyzing",
  "considering",
  "processing",
  "reflecting",
  "evaluating",
];

const LABELS: Partial<Record<StatusType, string>> = {
  [Status.COMPRESSING]: "compressing context",
  [Status.AWAITING_APPROVAL]: "awaiting approval",
};

interface CyclingStatusProps {
  status: StatusType;
  isStreaming: boolean;
}

export function CyclingStatus({ status, isStreaming }: CyclingStatusProps) {
  const [verb, setVerb] = useState(VERBS[0]);

  useEffect(() => {
    if (isStreaming) {
      setVerb(VERBS[Math.floor(Math.random() * VERBS.length)]);
    }
  }, [isStreaming]);

  const label = LABELS[status];
  if (label) return <text><span fg={colors.text.muted}>{label}</span></text>;

  return <text><span fg={colors.text.muted}>{verb}</span></text>;
}
