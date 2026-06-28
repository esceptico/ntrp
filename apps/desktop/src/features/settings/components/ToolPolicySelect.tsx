import type { ToolOverrideDecision } from "@/api/types";
import { SegmentedControl, SegmentedControlItem } from "@/components/ui/SegmentedControl";

export const TOOL_POLICY_DECISIONS: Array<{ value: ToolOverrideDecision; label: string }> = [
  { value: "approve", label: "Approve" },
  { value: "ask", label: "Ask" },
  { value: "deny", label: "Deny" },
];

/**
 * Approve / Ask / Deny segmented control for a tool's approval policy. The
 * builtin-tools tab and the MCP server tools section render different rows
 * around it (one has an enable switch, the other a policy badge), but the
 * policy selector itself is identical — so it lives here as one source.
 */
export function ToolPolicySelect({
  value,
  onChange,
}: {
  value: ToolOverrideDecision;
  onChange: (decision: ToolOverrideDecision) => void;
}) {
  return (
    <SegmentedControl
      size="sm"
      value={value}
      onChange={(v) => onChange(v as ToolOverrideDecision)}
    >
      {TOOL_POLICY_DECISIONS.map((d) => (
        <SegmentedControlItem key={d.value} value={d.value}>
          {d.label}
        </SegmentedControlItem>
      ))}
    </SegmentedControl>
  );
}
