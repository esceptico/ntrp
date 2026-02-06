import { useCallback, useRef, useState } from "react";
import type { Key } from "./useKeypress.js";

interface InlineTextInput {
  value: string;
  cursorPos: number;
  setValue: (value: string) => void;
  reset: () => void;
  handleKey: (key: Key) => boolean;
}

export function useInlineTextInput(): InlineTextInput {
  const [value, setValue] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const valueRef = useRef(value);
  const cursorRef = useRef(cursorPos);
  valueRef.current = value;
  cursorRef.current = cursorPos;

  const reset = useCallback(() => {
    setValue("");
    setCursorPos(0);
  }, []);

  const handleKey = useCallback(
    (key: Key): boolean => {
      if (key.name === "left") {
        setCursorPos((p) => Math.max(0, p - 1));
        return true;
      }
      if (key.name === "right") {
        setCursorPos((p) => Math.min(valueRef.current.length, p + 1));
        return true;
      }
      if (key.name === "backspace" || key.name === "delete") {
        const pos = cursorRef.current;
        if (pos > 0) {
          setValue((t) => t.slice(0, pos - 1) + t.slice(pos));
          setCursorPos((p) => p - 1);
        }
        return true;
      }
      if (key.insertable && key.sequence && !key.ctrl && !key.meta) {
        const pos = cursorRef.current;
        const seq = key.sequence;
        setValue((t) => t.slice(0, pos) + seq + t.slice(pos));
        setCursorPos((p) => p + seq.length);
        return true;
      }
      return false;
    },
    []
  );

  return { value, cursorPos, setValue, reset, handleKey };
}
