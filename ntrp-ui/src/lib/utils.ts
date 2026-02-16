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

export function formatAge(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  if (diff < 0) return "now";

  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${Math.max(1, mins)}m`;

  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;

  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  if (days < 30) return `${Math.floor(days / 7)}w`;

  return `${Math.floor(days / 30)}mo`;
}

export interface ScrollWindow {
  scrollOffset: number;
  canScrollUp: boolean;
  canScrollDown: boolean;
}
