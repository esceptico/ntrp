declare module "*.css";

interface Window {
  ntrpDesktop?: {
    version: () => string;
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
      connect: (config: { serverUrl: string; apiKey: string }, sessionId: string) => Promise<string>;
      disconnect: (connectionId: string) => Promise<void>;
      onData: (
        callback: (payload: {
          connectionId: string;
          event?: unknown;
          error?: string;
        }) => void,
      ) => () => void;
    };
    shell: {
      /** Opens a file or directory in the OS default application. Resolves
       *  to "" on success, an error message otherwise. */
      openPath: (path: string) => Promise<string>;
    };
  };
}
