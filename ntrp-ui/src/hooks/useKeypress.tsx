/**
 * Custom keyboard handling that bypasses Ink's useInput.
 * Supports bracketed paste mode for proper paste handling.
 */
import type React from "react";
import { useStdin } from "ink";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";

const ESC = "\x1b";
const ESC_TIMEOUT = 50;

// Bracketed paste mode escape sequences
const PASTE_START = "\x1b[200~";
const PASTE_END = "\x1b[201~";

// Key escape sequence map for special keys
const KEY_MAP: Record<string, { name: string; shift?: boolean }> = {
  // Arrow keys (normal and application mode)
  "[A": { name: "up" }, "OA": { name: "up" },
  "[B": { name: "down" }, "OB": { name: "down" },
  "[C": { name: "right" }, "OC": { name: "right" },
  "[D": { name: "left" }, "OD": { name: "left" },
  // Navigation
  "[H": { name: "home" }, "OH": { name: "home" }, "[1~": { name: "home" },
  "[F": { name: "end" }, "OF": { name: "end" }, "[4~": { name: "end" },
  "[3~": { name: "delete" },
  "[Z": { name: "tab", shift: true },
};

// CSI u protocol keycodes
const CSI_U_MAP: Record<number, string> = {
  9: "tab", 13: "return", 27: "escape", 127: "backspace",
};

export interface Key {
  name: string;
  ctrl: boolean;
  meta: boolean;
  shift: boolean;
  insertable: boolean;
  sequence: string;
  /** True when this is pasted content (via bracketed paste mode) */
  isPasted?: boolean;
}

export type KeypressHandler = (key: Key) => void;

interface KeypressContextValue {
  subscribe: (handler: KeypressHandler) => void;
  unsubscribe: (handler: KeypressHandler) => void;
}

const KeypressContext = createContext<KeypressContextValue | undefined>(undefined);

export function useKeypressContext() {
  const context = useContext(KeypressContext);
  if (!context) {
    throw new Error("useKeypressContext must be used within a KeypressProvider");
  }
  return context;
}

/**
 * Parses raw stdin data into key events.
 */
function* emitKeys(keypressHandler: KeypressHandler): Generator<void, void, string> {
  while (true) {
    let ch = yield;
    let sequence = ch;
    let escaped = false;

    let name: string | undefined = undefined;
    let ctrl = false;
    let meta = false;
    let shift = false;
    let code: string | undefined = undefined;
    let insertable = false;

    if (ch === ESC) {
      escaped = true;
      ch = yield;
      sequence += ch;

      if (ch === ESC) {
        ch = yield;
        sequence += ch;
      }
    }

    if (escaped && (ch === "O" || ch === "[")) {
      code = ch;
      let modifier = 0;

      if (ch === "O") {
        ch = yield;
        sequence += ch;
        if (ch >= "0" && ch <= "9") {
          modifier = parseInt(ch, 10) - 1;
          ch = yield;
          sequence += ch;
        }
        code += ch;
      } else if (ch === "[") {
        ch = yield;
        sequence += ch;

        const cmdStart = sequence.length - 1;

        // Collect digits
        while (ch >= "0" && ch <= "9") {
          ch = yield;
          sequence += ch;
        }

        // Handle modifier after semicolon
        if (ch === ";") {
          while (ch === ";") {
            ch = yield;
            sequence += ch;
            while (ch >= "0" && ch <= "9") {
              ch = yield;
              sequence += ch;
            }
          }
        }

        const cmd = sequence.slice(cmdStart);
        let match;

        // CSI u format: keycode;modifier u (modern terminal protocol)
        if ((match = /^(\d+)(?:;(\d+))?(?::(\d+))?u$/.exec(cmd))) {
          const keycode = parseInt(match[1], 10);
          modifier = parseInt(match[2] ?? "1", 10) - 1;
          const event = match[3] ? parseInt(match[3], 10) : 1;
          
          if (event === 3) continue; // Ignore key release
          
          name = CSI_U_MAP[keycode];
          if (!name && keycode >= 97 && keycode <= 122) { name = String.fromCharCode(keycode); insertable = true; }
          else if (!name && keycode >= 65 && keycode <= 90) { name = String.fromCharCode(keycode + 32); insertable = true; }
          
          ctrl = !!(modifier & 4);
          meta = !!(modifier & 10);
          shift = !!(modifier & 1);
        } else if ((match = /^(\d+)(?:;(\d+))?([~^$])$/.exec(cmd))) {
          code += match[1] + match[3];
          modifier = parseInt(match[2] ?? "1", 10) - 1;
        } else if ((match = /^(\d+)?(?:;(\d+))?([A-Za-z])$/.exec(cmd))) {
          code += match[3];
          modifier = parseInt(match[2] ?? match[1] ?? "1", 10) - 1;
        } else {
          code += cmd;
        }
      }

      // Only apply modifier bits if not already set by CSI u parsing
      if (code && !name) {
        ctrl = !!(modifier & 4);
        meta = !!(modifier & 10);
        shift = !!(modifier & 1);

        const keyInfo = KEY_MAP[code];
        if (keyInfo) {
          name = keyInfo.name;
          if (keyInfo.shift) shift = true;
        }
      }
    } else if (ch === "\r" || ch === "\n") {
      name = "return";
      meta = escaped;
    } else if (ch === "\t") {
      name = "tab";
      meta = escaped;
    } else if (ch === "\b" || ch === "\x7f") {
      name = "backspace";
      meta = escaped;
    } else if (ch === ESC) {
      name = "escape";
      meta = escaped;
    } else if (ch === " ") {
      name = "space";
      meta = escaped;
      insertable = true;
    } else if (!escaped && ch <= "\x1a") {
      name = String.fromCharCode(ch.charCodeAt(0) + "a".charCodeAt(0) - 1);
      ctrl = true;
    } else if (/^[0-9A-Za-z]$/.exec(ch) !== null) {
      name = ch.toLowerCase();
      shift = /^[A-Z]$/.exec(ch) !== null;
      meta = escaped;
      insertable = true;
    } else if (sequence === `${ESC}${ESC}`) {
      name = "escape";
      meta = true;
    } else if (escaped) {
      name = ch.length ? undefined : "escape";
      meta = true;
    } else {
      insertable = true;
    }

    if (sequence.length !== 0 && (name !== undefined || escaped || insertable)) {
      keypressHandler({
        name: name || "",
        ctrl,
        meta,
        shift,
        insertable,
        sequence,
      });
    }
  }
}

// macOS Option+key handling for word deletion (Option+Backspace)
// Works when terminal sends Option as high-bit (byte > 127) or ESC prefix
// Requires terminal config:
// - Cursor: Settings → terminal.integrated.macOptionIsMeta: true
// - iTerm2: Preferences → Profiles → Keys → Left Option Key: Esc+
// - Terminal.app: Preferences → Profiles → Keyboard → Use Option as Meta Key
// Fallback: use Ctrl+W for backward word delete
function normalizeOptionKey(data: Buffer | string): string {
  if (Buffer.isBuffer(data)) {
    if (data[0] > 127 && data.length === 1) {
      return ESC + String.fromCharCode(data[0] - 128);
    }
    return data.toString("utf8");
  }
  return data;
}

function createDataListener(keypressHandler: KeypressHandler) {
  const parser = emitKeys(keypressHandler);
  parser.next(); // Prime the generator

  let timeoutId: NodeJS.Timeout;
  
  // State for multi-chunk paste handling
  let isPasting = false;
  let pasteBuffer = "";
  
  return (data: Buffer | string) => {
    const input = normalizeOptionKey(data);
    clearTimeout(timeoutId);
    
    let remaining = input;
    
    while (remaining.length > 0) {
      if (isPasting) {
        // Look for paste end marker
        const endIdx = remaining.indexOf(PASTE_END);
        if (endIdx !== -1) {
          // Found end - complete the paste
          pasteBuffer += remaining.slice(0, endIdx);
          remaining = remaining.slice(endIdx + PASTE_END.length);
          isPasting = false;
          
          // Emit paste as single key event
          if (pasteBuffer.length > 0) {
            keypressHandler({
              name: "paste",
              ctrl: false,
              meta: false,
              shift: false,
              insertable: true,
              sequence: pasteBuffer,
              isPasted: true,
            });
          }
          pasteBuffer = "";
        } else {
          // No end marker - buffer entire remaining data
          pasteBuffer += remaining;
          remaining = "";
        }
      } else {
        // Look for paste start marker
        const startIdx = remaining.indexOf(PASTE_START);
        if (startIdx !== -1) {
          // Process normal chars before paste start
          const beforePaste = remaining.slice(0, startIdx);
          for (const char of beforePaste) {
            parser.next(char);
          }
          
          // Start pasting
          remaining = remaining.slice(startIdx + PASTE_START.length);
          isPasting = true;
          pasteBuffer = "";
        } else {
          // No paste marker - process normally
          for (const char of remaining) {
            parser.next(char);
          }
          remaining = "";
        }
      }
    }
    
    if (input.length !== 0 && !isPasting) {
      timeoutId = setTimeout(() => parser.next(""), ESC_TIMEOUT);
    }
  };
}

export function KeypressProvider({ children }: { children: React.ReactNode }) {
  const { stdin, setRawMode } = useStdin();

  const subscribersRef = useRef<Set<KeypressHandler>>(new Set());

  const subscribe = useCallback((handler: KeypressHandler) => {
    subscribersRef.current.add(handler);
  }, []);

  const unsubscribe = useCallback((handler: KeypressHandler) => {
    subscribersRef.current.delete(handler);
  }, []);

  const broadcast = useCallback((key: Key) => {
    subscribersRef.current.forEach((handler) => handler(key));
  }, []);

  useEffect(() => {
    const wasRaw = stdin.isRaw;
    if (!wasRaw) {
      setRawMode(true);
    }

    // Enable bracketed paste mode (widely supported)
    process.stdout.write("\x1b[?2004h");
    
    // Enable kitty keyboard protocol for modifier detection (e.g., Shift+Enter)
    // Supported: iTerm2, Kitty, Alacritty, WezTerm, foot
    // NOT supported: Cursor's integrated terminal (xterm.js), macOS Terminal.app
    // Fallback: use backslash before Enter for newlines
    process.stdout.write("\x1b[>1u");
    
    const dataListener = createDataListener(broadcast);

    stdin.on("data", dataListener);
    return () => {
      stdin.removeListener("data", dataListener);
      // Disable kitty keyboard protocol
      process.stdout.write("\x1b[<u");
      // Disable bracketed paste mode
      process.stdout.write("\x1b[?2004l");
      if (!wasRaw) {
        setRawMode(false);
      }
    };
  }, [stdin, setRawMode, broadcast]);

  return (
    <KeypressContext.Provider value={{ subscribe, unsubscribe }}>
      {children}
    </KeypressContext.Provider>
  );
}

export function useKeypress(
  onKeypress: KeypressHandler,
  { isActive }: { isActive: boolean }
) {
  const { subscribe, unsubscribe } = useKeypressContext();

  useEffect(() => {
    if (!isActive) {
      return;
    }

    subscribe(onKeypress);
    return () => {
      unsubscribe(onKeypress);
    };
  }, [isActive, onKeypress, subscribe, unsubscribe]);
}
