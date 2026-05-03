declare module "*.css";

interface Window {
  ntrpDesktop?: {
    version: () => string;
  };
}
