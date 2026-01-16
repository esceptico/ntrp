import { Box, Text } from "ink";
import { brand } from "./ui/colors.js";

const VERSION = "0.1.0";

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