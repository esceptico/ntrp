import { expect, test } from "bun:test";
import {
  factStatusLabel,
  factStatusTone,
  observationEvidenceLabel,
  observationEvidenceTone,
} from "../src/lib/memoryTrust.js";

test("labels fact statuses for trust inspection", () => {
  expect(factStatusLabel("active")).toBe("active");
  expect(factStatusLabel("pinned")).toBe("pinned");
  expect(factStatusLabel("superseded")).toBe("superseded");
  expect(factStatusTone("expired")).toBe("warn");
  expect(factStatusTone("archived")).toBe("bad");
});

test("labels pattern evidence levels by trust strength", () => {
  expect(observationEvidenceLabel("unsupported")).toBe("unsupported");
  expect(observationEvidenceLabel("single_fact_seed")).toBe("single source");
  expect(observationEvidenceLabel("multi_fact")).toBe("multi-source");
  expect(observationEvidenceLabel("temporal_pattern")).toBe("temporal");
  expect(observationEvidenceTone("unsupported")).toBe("bad");
  expect(observationEvidenceTone("single_fact_seed")).toBe("warn");
  expect(observationEvidenceTone("multi_fact")).toBe("ok");
});

