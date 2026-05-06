import type { FactStatus, FactTrustStatus, ObservationEvidenceLevel } from "../api";

type PillTone = "neutral" | "accent" | "ok" | "warn" | "bad";

export function factStatusLabel(status: FactTrustStatus): string {
  return status;
}

export function factStatusFilterLabel(status: FactStatus): string {
  if (status === "all") return "All statuses";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function factStatusTone(status: FactTrustStatus): PillTone {
  switch (status) {
    case "active":
      return "neutral";
    case "pinned":
      return "accent";
    case "temporary":
      return "warn";
    case "expired":
      return "warn";
    case "superseded":
      return "bad";
    case "archived":
      return "bad";
  }
}

export function observationEvidenceLabel(level: ObservationEvidenceLevel): string {
  switch (level) {
    case "unsupported":
      return "unsupported";
    case "single_fact_seed":
      return "single source";
    case "multi_fact":
      return "multi-source";
    case "temporal_pattern":
      return "temporal";
  }
}

export function observationEvidenceTone(level: ObservationEvidenceLevel): PillTone {
  switch (level) {
    case "unsupported":
      return "bad";
    case "single_fact_seed":
      return "warn";
    case "multi_fact":
      return "ok";
    case "temporal_pattern":
      return "accent";
  }
}
