import { GlobalRegistrator } from "@happy-dom/global-registrator";

// Single global test DOM for the whole bun test suite. Replaces the per-file
// JSDOM realms + hand-rolled polyfills that the suite used to carry.
GlobalRegistrator.register({ url: "http://localhost" });

// React's act() environment flag — every interaction test renders under act.
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT ??= true;
