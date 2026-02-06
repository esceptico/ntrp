import { createRequire } from "module";
import { Box, Text } from "ink";
import { useAccentColor } from "../hooks/index.js";

const require = createRequire(import.meta.url);
const { version: VERSION } = require("../../package.json");

const LOGO_LINE_1 = "█▄ █ ▀█▀ █▀▄ █▀▄";
const LOGO_LINE_2 = "█ ▀█  █  █▀▄ █▀▀";

export function Welcome() {
  const { accentValue } = useAccentColor();

  return (
    <Box flexDirection="column" marginTop={1} marginLeft={1} marginBottom={1}>
      <Text color={accentValue}>{LOGO_LINE_1}</Text>
      <Text>
        <Text color={accentValue}>{LOGO_LINE_2}</Text>
        <Text dimColor> v{VERSION}</Text>
      </Text>
    </Box>
  );
}