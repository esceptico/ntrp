import { useAccentColor } from "../hooks/index.js";
import { colors } from "./ui/colors.js";

const LOGO_TOP = "█▄ █ ▀█▀ █▀▄ █▀▄";
const LOGO_BOT = "█ ▀█  █  █▀▄ █▀▀";

export function Welcome() {
  const { accentValue } = useAccentColor();

  return (
    <box flexDirection="column" marginTop={1} marginLeft={1} marginBottom={1}>
      <text><span fg={accentValue}>{LOGO_TOP}</span></text>
      <text>
        <span fg={accentValue}>{LOGO_BOT}</span>
        <span fg={colors.text.muted}> v0.1.0</span>
      </text>
    </box>
  );
}
