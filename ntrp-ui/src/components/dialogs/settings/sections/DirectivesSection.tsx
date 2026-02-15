import { colors } from "../../../ui/colors.js";
import { TextEditArea } from "../../../ui/TextEditArea.js";
import { Hints } from "../../../ui/index.js";

interface DirectivesSectionProps {
  content: string;
  cursorPos: number;
  editing: boolean;
  saving: boolean;
  accent: string;
  height: number;
}

export function DirectivesSection({
  content,
  cursorPos,
  editing,
  saving,
  accent,
  height,
}: DirectivesSectionProps) {
  if (saving) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>Saving...</span></text>
      </box>
    );
  }

  if (editing) {
    return (
      <box flexDirection="column" height={height}>
        <box marginBottom={1}>
          <text><span fg={accent}>Editing directives</span></text>
        </box>
        <box flexGrow={1} overflow="hidden">
          <TextEditArea
            value={content}
            cursorPos={cursorPos}
            onValueChange={() => {}}
            onCursorChange={() => {}}
            placeholder="Enter directives..."
          />
        </box>
        <box marginTop={1}>
          <Hints items={[["ctrl+s", "save"], ["esc", "cancel"]]} />
        </box>
      </box>
    );
  }

  if (!content) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No directives set.</span></text>
        <box marginTop={1}>
          <Hints items={[["enter", "edit"]]} />
        </box>
      </box>
    );
  }

  const lines = content.split("\n");
  return (
    <box flexDirection="column" height={height}>
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        {lines.map((line, i) => (
          <text key={i}><span fg={colors.text.secondary}>{line || " "}</span></text>
        ))}
      </box>
      <box marginTop={1}>
        <Hints items={[["enter", "edit"]]} />
      </box>
    </box>
  );
}
