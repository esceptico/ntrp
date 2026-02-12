/**
 * Thin adapter around OpenTUI's useKeyboard.
 * Maps OpenTUI's KeyEvent to our Key type for backward compatibility with hooks.
 * No provider needed — OpenTUI handles raw mode, kitty protocol, etc.
 */
import { useCallback, useEffect, useRef } from "react";
import { useKeyboard } from "@opentui/react";
import type { KeyEvent } from "@opentui/core";

export interface Key {
  name: string;
  ctrl: boolean;
  meta: boolean;
  shift: boolean;
  insertable: boolean;
  sequence: string;
  isPasted?: boolean;
}

export type KeypressHandler = (key: Key) => void;

function toKey(event: KeyEvent): Key {
  const isModifier = event.ctrl || event.meta;
  const isPrintable = event.sequence.length === 1 && !isModifier;
  const isNamedInsertable = event.name === "space" || event.name === "return";

  return {
    name: event.name,
    ctrl: event.ctrl,
    meta: event.meta,
    shift: event.shift,
    insertable: isPrintable || isNamedInsertable,
    sequence: event.sequence,
  };
}

/**
 * Drop-in replacement for the old useKeypress(handler, { isActive }).
 * Uses OpenTUI's useKeyboard under the hood.
 */
export function useKeypress(
  onKeypress: KeypressHandler,
  { isActive }: { isActive: boolean }
) {
  const handlerRef = useRef(onKeypress);
  handlerRef.current = onKeypress;
  const activeRef = useRef(isActive);
  activeRef.current = isActive;

  useKeyboard((event) => {
    if (!activeRef.current) return;
    handlerRef.current(toKey(event));
  });
}
