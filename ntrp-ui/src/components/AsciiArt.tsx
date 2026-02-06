import { createRequire } from "module";
import { Box, Text } from "ink";
import { brand } from "./ui/colors.js";

const require = createRequire(import.meta.url);
const { version: VERSION } = require("../../package.json");

const LOGO_LINE_1 = "█▄ █ ▀█▀ █▀▄ █▀▄";
const LOGO_LINE_2 = "█ ▀█  █  █▀▄ █▀▀";

export function Welcome() {
  return (
    <Box flexDirection="column" marginTop={1} marginLeft={1} marginBottom={1}>
      <Text color={brand.primary}>{LOGO_LINE_1}</Text>
      <Text>
        <Text color={brand.primary}>{LOGO_LINE_2}</Text>
        <Text dimColor> v{VERSION}</Text>
      </Text>
    </Box>
  );
}