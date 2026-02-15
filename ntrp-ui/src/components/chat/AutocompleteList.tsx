import { useRef } from "react";
import type { SlashCommand } from "../../types.js";
import { colors } from "../ui/index.js";
import { SplitBorder } from "../ui/border.js";

interface AutocompleteListProps {
  commands: readonly SlashCommand[];
  selectedIndex: number;
  accentValue: string;
}

const MAX_VISIBLE = 10;

export function AutocompleteList({ commands, selectedIndex, accentValue }: AutocompleteListProps) {
  const maxName = Math.max(...commands.map((c) => c.name.length));
  const visibleCount = Math.min(MAX_VISIBLE, commands.length);
  const scrollTopRef = useRef(0);

  // Keep selected item in view by adjusting the window
  let scrollTop = scrollTopRef.current;
  if (selectedIndex < scrollTop) {
    scrollTop = selectedIndex;
  } else if (selectedIndex >= scrollTop + visibleCount) {
    scrollTop = selectedIndex - visibleCount + 1;
  }
  scrollTopRef.current = scrollTop;

  const visible = commands.slice(scrollTop, scrollTop + visibleCount);

  return (
    <box
      border={SplitBorder.border}
      borderColor={colors.border}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <box flexDirection="column" backgroundColor={colors.background.menu}>
        {visible.map((cmd, vi) => {
          const i = scrollTop + vi;
          const isSelected = i === selectedIndex;
          const display = `/${cmd.name}`.padEnd(maxName + 3);

          return (
            <box
              key={cmd.name}
              paddingLeft={2}
              paddingRight={2}
              backgroundColor={isSelected ? accentValue : undefined}
              flexDirection="row"
            >
              <text fg={isSelected ? colors.contrast : colors.text.primary} flexShrink={0}>
                {display}
              </text>
              {cmd.description ? (
                <text fg={isSelected ? colors.contrast : colors.text.muted} wrapMode="none">
                  {cmd.description}
                </text>
              ) : null}
            </box>
          );
        })}
      </box>
    </box>
  );
}
