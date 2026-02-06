import { createRequire } from "module";
import { Box, Text } from "ink";
import { useAccentColor } from "../hooks/index.js";

const require = createRequire(import.meta.url);
const { version: VERSION } = require("../../package.json");

const LOGO_TOP = "█▄ █ ▀█▀ █▀▄ █▀▄";
const LOGO_BOT = "█ ▀█  █  █▀▄ █▀▀";

export function Welcome() {
  const { accentValue } = useAccentColor();

  return (
    <Box flexDirection="column" marginTop={1} marginLeft={1} marginBottom={1}>
      <Text color={accentValue}>{LOGO_TOP}</Text>
      <Text>
        <Text color={accentValue}>{LOGO_BOT}</Text>
        <Text dimColor> v{VERSION}</Text>
      </Text>
    </Box>
  );
}