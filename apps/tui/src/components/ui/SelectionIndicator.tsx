import { colors } from "./colors.js";
import { INDICATOR_SELECTED, INDICATOR_UNSELECTED } from "../../lib/constants.js";

interface SelectionIndicatorProps {
  selected: boolean;
  accent?: string;
}

export function SelectionIndicator({ selected, accent = colors.text.primary }: SelectionIndicatorProps) {
  return (
    <span fg={selected ? accent : colors.text.disabled}>
      {selected ? INDICATOR_SELECTED : INDICATOR_UNSELECTED}
    </span>
  );
}
