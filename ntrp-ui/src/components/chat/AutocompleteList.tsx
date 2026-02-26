import type { SlashCommand } from "../../types.js";
import { BaseSelectionList, colors } from "../ui/index.js";
import { SplitBorder } from "../ui/border.js";

interface AutocompleteListProps {
  commands: readonly SlashCommand[];
  selectedIndex: number;
  accentValue: string;
}

const MAX_VISIBLE = 10;

export function AutocompleteList({ commands, selectedIndex, accentValue }: AutocompleteListProps) {
  const maxName = commands.length > 0 ? Math.max(...commands.map((c) => c.name.length)) : 0;

  return (
    <box
      border={SplitBorder.border}
      borderColor={colors.border}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <BaseSelectionList
        items={commands}
        selectedIndex={selectedIndex}
        visibleLines={Math.min(MAX_VISIBLE, commands.length || MAX_VISIBLE)}
        showIndicator={false}
        renderItem={(cmd, ctx) => {
          const display = `/${cmd.name}`.padEnd(maxName + 3);
          return (
            <box
              paddingLeft={2}
              paddingRight={2}
              backgroundColor={ctx.isSelected ? accentValue : colors.background.menu}
              flexDirection="row"
            >
              <text fg={ctx.isSelected ? colors.contrast : colors.text.primary} flexShrink={0}>
                {display}
              </text>
              {cmd.description ? (
                <text fg={ctx.isSelected ? colors.contrast : colors.text.muted} wrapMode="none">
                  {cmd.description}
                </text>
              ) : null}
            </box>
          );
        }}
      />
    </box>
  );
}
