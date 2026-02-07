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

export function wrapText(text: string, width: number): string[] {
  if (width <= 0) return [text];
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
  return lines;
}

export interface ScrollWindow {
  scrollOffset: number;
  canScrollUp: boolean;
  canScrollDown: boolean;
}
