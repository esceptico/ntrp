declare module "*.css";

interface Window {
  ntrpDesktop?: {
    version: () => string;
    config: {
      get: () => Promise<{ serverUrl: string; apiKey: string }>;
      set: (config: { serverUrl: string; apiKey: string }) => Promise<{ serverUrl: string; apiKey: string }>;
    };
  };
}
