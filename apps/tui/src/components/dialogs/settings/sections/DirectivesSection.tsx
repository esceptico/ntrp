import { colors } from "../../../ui/colors.js";
import { TextEditArea } from "../../../ui/TextEditArea.js";
import type { UseDirectivesResult } from "../../../../hooks/settings/useDirectives.js";

interface DirectivesSectionProps {
  directives: UseDirectivesResult;
  accent: string;
  height: number;
}

export function DirectivesSection({ directives: d, accent, height }: DirectivesSectionProps) {
  if (d.savingDirectives) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>Saving...</span></text>
      </box>
    );
  }

  if (d.editingDirectives) {
    return (
      <box flexDirection="column" height={height}>
        <box marginBottom={1}>
          <text><span fg={accent}>Editing instructions</span></text>
        </box>
        <box flexGrow={1} overflow="hidden">
          <TextEditArea
            value={d.directivesContent}
            cursorPos={d.directivesCursorPos}
            onValueChange={() => {}}
            onCursorChange={() => {}}
            placeholder="Enter directives..."
          />
        </box>
      </box>
    );
  }

  if (!d.directivesContent) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No directives set.</span></text>
      </box>
    );
  }

  const lines = d.directivesContent.split("\n");
  return (
    <box flexDirection="column" height={height}>
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        {lines.map((line, i) => (
          <text key={i}><span fg={colors.text.secondary}>{line || " "}</span></text>
        ))}
      </box>
    </box>
  );
}
