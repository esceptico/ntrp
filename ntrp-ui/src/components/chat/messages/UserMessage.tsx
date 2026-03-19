import { memo, useMemo } from "react";
import { useAccentColor } from "../../../hooks/index.js";
import { colors } from "../../ui/colors.js";
import { SplitBorder } from "../../ui/border.js";
import { getImagePixels } from "../../../lib/image-preview.js";

interface UserMessageProps {
  content: string;
  images?: Array<{ media_type: string; data: string }>;
  editing?: boolean;
}

export const UserMessage = memo(function UserMessage({ content, images, editing }: UserMessageProps) {
  const { accentValue } = useAccentColor();

  const previews = useMemo(() => {
    if (!images?.length) return null;
    return images.map((img) => getImagePixels(img.data, img.media_type));
  }, [images]);

  return (
    <box
      overflow="hidden"
      border={SplitBorder.border}
      borderColor={editing ? colors.status.warning : accentValue}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <box
        paddingTop={1}
        paddingBottom={1}
        paddingLeft={2}
        paddingRight={2}
        backgroundColor={colors.background.panel}
        flexShrink={0}
      >
        {previews && previews.map((rows, i) => (
          <box key={i} flexDirection="column" flexShrink={0} paddingBottom={content ? 1 : 0}>
            {rows.map((row, y) => (
              <text key={y}>
                {row.pixels.map((p, x) => (
                  <span key={x} fg={p.fg} bg={p.bg}>▀</span>
                ))}
              </text>
            ))}
          </box>
        ))}
        {content && <text fg={colors.text.primary}>{content}</text>}
        {editing && <text fg={colors.status.warning}>editing</text>}
      </box>
    </box>
  );
});
