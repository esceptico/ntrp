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

  const borderProps = editing
    ? { border: true as const, borderColor: colors.status.warning }
    : { border: SplitBorder.border, borderColor: accentValue, customBorderChars: SplitBorder.customBorderChars };

  return (
    <box overflow="hidden" {...borderProps}>
      <box
        paddingTop={editing ? 0 : 1}
        paddingBottom={editing ? 0 : 1}
        paddingLeft={editing ? 1 : 2}
        paddingRight={editing ? 1 : 2}
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
      </box>
    </box>
  );
});
