import { colors } from "../ui/index.js";

interface HelpPanelProps {
  accentValue: string;
}

export function HelpPanel({ accentValue }: HelpPanelProps) {
  const D = colors.text.muted;
  return (
    <box flexDirection="column" paddingLeft={2}>
      <box gap={4}>
        <box flexDirection="column">
          <text><span fg={accentValue}>/</span> for commands</text>
          <text><span fg={accentValue}>\⏎</span> or <span fg={accentValue}>shift+⏎</span> newline</text>
        </box>
        <box flexDirection="column">
          <text><span fg={D}>ctrl+k  kill to end</span></text>
          <text><span fg={D}>ctrl+u  kill to start</span></text>
          <text><span fg={D}>ctrl+w  kill word ←</span></text>
        </box>
        <box flexDirection="column">
          <text><span fg={D}>ctrl+a  home</span></text>
          <text><span fg={D}>ctrl+e  end</span></text>
          <text><span fg={D}>esc     clear input</span></text>
        </box>
        <box flexDirection="column">
          <text><span fg={D}>↑/↓      navigate autocomplete</span></text>
          <text><span fg={D}>tab      confirm selection</span></text>
          <text><span fg={D}>ctrl+←→  word jump</span></text>
        </box>
      </box>
    </box>
  );
}
