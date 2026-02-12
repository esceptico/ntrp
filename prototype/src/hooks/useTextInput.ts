import { useCallback, useRef } from "react";
import type { Key } from "./useKeypress.js";

interface UseTextInputOptions {
  text: string;
  cursorPos: number;
  setText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
}

interface UseTextInputResult {
  handleKey: (key: Key) => boolean;
  findPrevWordBoundary: (pos: number) => number;
  findNextWordBoundary: (pos: number) => number;
}

export function useTextInput({
  text,
  cursorPos,
  setText,
  setCursorPos,
}: UseTextInputOptions): UseTextInputResult {
  const textRef = useRef(text);
  textRef.current = text;
  const cursorRef = useRef(cursorPos);
  cursorRef.current = cursorPos;

  const findPrevWordBoundary = useCallback((pos: number) => {
    const v = textRef.current;
    let p = pos - 1;
    while (p > 0 && /\s/.test(v[p])) p--;
    while (p > 0 && /\S/.test(v[p - 1])) p--;
    return Math.max(0, p);
  }, []);

  const findNextWordBoundary = useCallback((pos: number) => {
    const v = textRef.current;
    let p = pos;
    while (p < v.length && /\S/.test(v[p])) p++;
    while (p < v.length && /\s/.test(v[p])) p++;
    return p;
  }, []);

  const moveCursor = useCallback(
    (newPos: number) => {
      setCursorPos(newPos);
      cursorRef.current = newPos;
    },
    [setCursorPos]
  );

  const insertAt = useCallback(
    (pos: number, str: string) => {
      setText((v) => v.slice(0, pos) + str + v.slice(pos));
      moveCursor(pos + str.length);
    },
    [setText, moveCursor]
  );

  const handleKey = useCallback(
    (key: Key): boolean => {
      const pos = cursorRef.current;

      if (key.isPasted && key.sequence) {
        insertAt(pos, key.sequence);
        return true;
      }

      if ((key.name === "backspace" && key.meta) || (key.name === "w" && key.ctrl)) {
        if (pos === 0) return true;
        const newPos = findPrevWordBoundary(pos);
        setText((v) => v.slice(0, newPos) + v.slice(pos));
        moveCursor(newPos);
        return true;
      }

      if (key.name === "backspace") {
        if (pos > 0) {
          setText((v) => v.slice(0, pos - 1) + v.slice(pos));
          moveCursor(pos - 1);
        }
        return true;
      }

      if (key.name === "delete") {
        if (pos < text.length) {
          setText((v) => v.slice(0, pos) + v.slice(pos + 1));
        }
        return true;
      }

      if (key.name === "k" && key.ctrl) {
        setText((v) => v.slice(0, pos));
        return true;
      }

      if (key.name === "u" && key.ctrl) {
        setText((v) => v.slice(pos));
        moveCursor(0);
        return true;
      }

      if ((key.name === "left" && key.meta) || (key.name === "left" && key.ctrl)) {
        moveCursor(findPrevWordBoundary(pos));
        return true;
      }
      if ((key.name === "right" && key.meta) || (key.name === "right" && key.ctrl)) {
        moveCursor(findNextWordBoundary(pos));
        return true;
      }
      if (key.name === "b" && key.meta) {
        moveCursor(findPrevWordBoundary(pos));
        return true;
      }
      if (key.name === "f" && key.meta) {
        moveCursor(findNextWordBoundary(pos));
        return true;
      }

      if (key.name === "left") {
        moveCursor(Math.max(0, pos - 1));
        return true;
      }
      if (key.name === "right") {
        moveCursor(Math.min(text.length, pos + 1));
        return true;
      }

      if (key.name === "home" || (key.name === "a" && key.ctrl)) {
        moveCursor(0);
        return true;
      }
      if (key.name === "end" || (key.name === "e" && key.ctrl)) {
        moveCursor(text.length);
        return true;
      }

      if (key.insertable && key.sequence && !key.ctrl && !key.meta) {
        const char = key.name === "return" ? "\n" : key.name === "space" ? " " : key.sequence;
        insertAt(pos, char);
        return true;
      }

      return false;
    },
    [text, findPrevWordBoundary, findNextWordBoundary, setText, moveCursor, insertAt]
  );

  return {
    handleKey,
    findPrevWordBoundary,
    findNextWordBoundary,
  };
}
