// Text utilities

export function truncateText(text: string, max: number, mode: 'end' | 'middle' | 'start' = 'end'): string {
  if (text.length <= max) return text;
  if (max <= 3) return '...'.slice(0, max);

  if (mode === 'end') {
    return text.slice(0, max - 3) + '...';
  }
  if (mode === 'start') {
    return '...' + text.slice(-(max - 3));
  }
  const half = Math.floor((max - 3) / 2);
  return text.slice(0, half) + '...' + text.slice(-half);
}

export function wrapText(text: string, width: number, indent: string = ''): string {
  if (text.length <= width) return text;
  const words = text.split(' ');
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    if (!line) {
      line = word;
    } else if (line.length + 1 + word.length <= width) {
      line += ' ' + word;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines.join('\n' + indent);
}

// Alias for backwards compatibility
export const truncate = (value: string, maxLen: number) => truncateText(value, maxLen, 'end');

// Value utilities

export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") {
    const trimmed = value.trim().toLowerCase();
    return !trimmed || trimmed === "<empty>" || trimmed === "empty";
  }
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value).length === 0;
  return false;
}

// Scroll window calculation (shared by list components)

export interface ScrollWindow {
  scrollOffset: number;
  canScrollUp: boolean;
  canScrollDown: boolean;
}

export function computeScrollWindow(
  selectedIndex: number,
  totalItems: number,
  visibleLines: number
): ScrollWindow {
  if (totalItems <= visibleLines) {
    return { scrollOffset: 0, canScrollUp: false, canScrollDown: false };
  }

  const padding = Math.floor(visibleLines / 3);
  let offset = selectedIndex - padding;
  offset = Math.max(0, offset);
  offset = Math.min(totalItems - visibleLines, offset);

  return {
    scrollOffset: offset,
    canScrollUp: offset > 0,
    canScrollDown: offset + visibleLines < totalItems,
  };
}
