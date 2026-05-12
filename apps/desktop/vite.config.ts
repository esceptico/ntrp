import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  root: "src",
  // Relative asset paths. Electron loads the packaged index.html via the
  // `file://` protocol, where the default absolute base (`/assets/...`)
  // resolves to the filesystem root instead of the app bundle —
  // resulting in a fully blank window on launch. `./` makes the script
  // and stylesheet refs relative to the html file location so they
  // resolve correctly inside the asar.
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../dist/renderer",
    emptyOutDir: true,
  },
});
