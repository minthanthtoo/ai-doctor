import { describe, expect, it } from "vitest";
import {
  buildPossibilityMap,
  evaluateSafety,
  type ClinicalFact,
  type ClinicalPack,
  type KernelInput,
  type Observation
} from "../src/index";
import packJson from "../../../src/ai_doctor/knowledge/v3/cardiometabolic_pack.json";

const pack = packJson as ClinicalPack;

function fact(display: string): ClinicalFact {
  return {
    factId: crypto.randomUUID(),
    revisionId: crypto.randomUUID(),
    kind: "symptom",
    display,
    value: {},
    verification: "user_reported",
    recordedAt: new Date().toISOString()
  };
}

function observation(kind: Observation["kind"], rawValue: Record<string, number>, rawUnit: string): Observation {
  return {
    observationId: crypto.randomUUID(),
    kind,
    rawValue,
    rawUnit,
    measuredAt: new Date().toISOString(),
    enteredAt: new Date().toISOString(),
    quality: "accepted",
    entryMethod: "manual"
  };
}

function input(overrides: Partial<KernelInput> = {}): KernelInput {
  return {
    profile: {
      profileId: crypto.randomUUID(),
      ageYears: 35,
      pregnancyStatus: "not_applicable",
      preferredLanguage: "en",
      jurisdiction: "MM"
    },
    facts: [fact("headache")],
    observations: [],
    answeredQuestionIds: ["q_chest_pain", "q_breathing", "q_neurologic"],
    snapshotHash: "a".repeat(64),
    pack,
    ...overrides
  };
}

describe("clinical safety kernel", () => {
  it("preempts routine reasoning for an affirmed red flag", () => {
    const assessment = evaluateSafety(input({ facts: [fact("chest pain now")] }));
    expect(assessment.urgency).toBe("emergency_now");
    expect(assessment.emergencyLock).toBe(true);
  });

  it("does not trigger an English-negated red flag", () => {
    const assessment = evaluateSafety(input({ facts: [fact("no chest pain")] }));
    expect(assessment.urgency).toBe("self_care_possible");
  });

  it("preempts for a released vital threshold", () => {
    const assessment = evaluateSafety(
      input({ observations: [observation("oxygen_saturation", { value: 88 }, "percent")] })
    );
    expect(assessment.urgency).toBe("emergency_now");
    expect(assessment.findings[0].ruleId).toBe("oxygen_very_low");
  });

  it("fails closed for missing population information", () => {
    const current = input();
    current.profile.ageYears = undefined;
    current.profile.pregnancyStatus = "unknown";
    const assessment = evaluateSafety(current);
    expect(assessment.urgency).toBe("insufficient_data");
    expect(assessment.missingInputs).toContain("age_years");
  });

  it("builds a non-authoritative possibility map only after safety clearance", () => {
    const current = input({ observations: [observation("blood_pressure", { systolic: 130, diastolic: 84 }, "mmHg")] });
    const assessment = evaluateSafety(current);
    const map = buildPossibilityMap(current, assessment);
    expect(map.authoritative).toBe(false);
    expect(map.hypotheses[0].terminologyId).toBe("possibility.blood_pressure_problem");
    expect(map.hypotheses[0].neverConfirmedAsDiagnosis).toBe(true);
  });
});
