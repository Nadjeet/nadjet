import type { components } from "@nadjet/api-client";

export type Verifier = components["schemas"]["VerifierResult"];

export type Confidence = "low" | "medium" | "high";

/** Display buckets for the verifier yes-probability; the exact value is never shown. */
export function confidenceOf(yesProbability: number | null | undefined): Confidence | null {
  if (yesProbability === null || yesProbability === undefined) return null;
  if (yesProbability >= 0.8) return "high";
  if (yesProbability >= 0.5) return "medium";
  return "low";
}

/** AI output that must be shown as uncertain (PRD NFR-SAFE-001). */
export function isUncertain(aiStatus: string | null, verifier: Verifier): boolean {
  if (aiStatus === null) return false;
  return (
    aiStatus === "possible" ||
    aiStatus === "insufficient_evidence" ||
    !verifier.available ||
    verifier.collision_visible === "cannot_judge"
  );
}
