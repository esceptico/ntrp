import importPlugin from "eslint-plugin-import";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

// bulletproof-react boundary enforcement (the only rule we run here — this
// config is intentionally not a full style linter). Two layers:
//   1. unidirectional: shared -> features -> app (no upward imports)
//   2. no cross-feature imports (compose features at the app layer)
// The integrated data layer (stores, actions, api) is SHARED — features may
// import it freely; it may not import features/app.

const FEATURES = [
  "chat",
  "sessions",
  "automations",
  "memory",
  "settings",
  "command-palette",
  "background-agents",
];

const SHARED = [
  "./src/lib",
  "./src/components/ui",
  "./src/stores",
  "./src/hooks",
  "./src/api",
  "./src/actions",
];

const sharedZones = SHARED.map((target) => ({
  target,
  from: ["./src/features", "./src/app"],
  message:
    "Unidirectional violation: shared code must not import from features/ or app/ (shared -> features -> app).",
}));

const crossFeatureZones = FEATURES.map((f) => ({
  target: `./src/features/${f}`,
  from: "./src/features",
  except: [`./${f}`],
  message: `Cross-feature import: features/${f} may not import another feature. Lift shared UI to src/components/ui, or shared logic to src/lib | src/actions | src/api | src/stores.`,
}));

export default tseslint.config({
  files: ["src/**/*.{ts,tsx}"],
  // react-hooks registered only so existing `// eslint-disable react-hooks/*`
  // comments resolve; its rules are intentionally NOT enabled here.
  plugins: { import: importPlugin, "react-hooks": reactHooks },
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
  settings: {
    "import/resolver": { typescript: { project: "./tsconfig.json" } },
  },
  rules: {
    "import/no-restricted-paths": [
      "error",
      {
        zones: [
          ...sharedZones,
          { target: "./src/features", from: "./src/app" },
          ...crossFeatureZones,
        ],
      },
    ],
  },
});
