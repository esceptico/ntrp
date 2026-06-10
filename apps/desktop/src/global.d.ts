declare module "*.css";
declare module "@fontsource-variable/geist";

interface Window {
  ntrpDesktop?: {
    version: () => string;
    app: {
      /** Reload the renderer (Cmd-R equivalent). */
      reload: () => Promise<void>;
      /** Quit the Electron app entirely. */
      quit: () => Promise<void>;
    };
    window: {
      /** Current native fullscreen state for the containing Electron window. */
      isFullScreen: () => Promise<boolean>;
      /** Subscribe to native fullscreen changes. */
      onFullScreenChange: (callback: (isFullScreen: boolean) => void) => () => void;
    };
    config: {
      get: () => Promise<{ serverUrl: string; apiKey: string }>;
      set: (config: { serverUrl: string; apiKey: string }) => Promise<{ serverUrl: string; apiKey: string }>;
    };
    api: {
      request: (
        config: { serverUrl: string; apiKey: string },
        request: { path: string; method?: string; body?: string; timeout?: number },
      ) => Promise<{
        ok: boolean;
        status: number;
        statusText: string;
        contentType: string;
        data: unknown;
        text: string;
      }>;
    };
    events: {
      connect: (
        config: { serverUrl: string; apiKey: string },
        sessionId: string,
        afterSeq?: number,
      ) => Promise<string>;
      disconnect: (connectionId: string) => Promise<void>;
      onData: (
        callback: (payload: {
          connectionId: string;
          event?: unknown;
          error?: string;
          closed?: boolean;
          reason?: string;
        }) => void,
      ) => () => void;
    };
    shell: {
      /** Opens a file or directory in the OS default application. Resolves
       *  to "" on success, an error message otherwise. */
      openPath: (path: string) => Promise<string>;
    };
    dialog: {
      /** Opens a native directory picker. Resolves null when cancelled. */
      selectDirectory: (options?: { defaultPath?: string }) => Promise<string | null>;
    };
    clipboard: {
      /** Writes text to the system clipboard via Electron's main process. */
      writeText: (text: string) => Promise<boolean>;
    };
    quickCapture: {
      /** Submit a message from the quick-capture window. Main process
       *  forwards it to the main window which calls its existing
       *  createSession + sendMessage. Resolves true on success. */
      submit: (message: string) => Promise<boolean>;
      /** Hide the quick-capture window without submitting. */
      close: () => Promise<void>;
      /** Register a new global shortcut for summoning the quick-capture
       *  window. Pass an empty string to disable. Resolves true on
       *  success, false if the OS refused (another app owns the chord). */
      setShortcut: (accelerator: string) => Promise<boolean>;
      /** Subscribe to forwarded quick-capture messages on the MAIN window.
       *  Returns an unsubscribe function. */
      onMessage: (callback: (message: string) => void) => () => void;
    };
  };
}
