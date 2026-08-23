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
    facts: [],
    observations: [],
    answeredQuestionIds: ["q_chest_pain", "q_breathing", "q_neurologic"],
    snapshotHash: "a".repeat(64),
    pack,
    ...overrides
  };
}

/**
 * Never-event corpus (CS-01): synthetic cases with mandatory outcomes.
 * A never-event is a presentation the kernel MUST lock to emergency_now,
 * or a benign control it MUST NOT. Any miss is a pack/kernel defect —
 * fix the knowledge or the kernel, never this corpus.
 */
interface NeverEventCase {
  id: string;
  display?: string;
  observation?: { kind: Observation["kind"]; value: Record<string, number>; unit: string };
  mustLock: boolean;
}

const NEVER_EVENTS: NeverEventCase[] = [
  // chest_pain
  { id: "cp-affirmed-en", display: "chest pain since morning", mustLock: true },
  { id: "cp-pressure", display: "chest pressure when walking", mustLock: true },
  { id: "cp-tightness-my", display: "ရင်ဘတ်အောင့်နေတယ်", mustLock: true },
  { id: "cp-negated", display: "no chest pain", mustLock: false },
  // breathing_difficulty
  { id: "br-shortness", display: "shortness of breath at rest", mustLock: true },
  { id: "br-cannot-breathe", display: "I cannot breathe properly", mustLock: true },
  { id: "br-my", display: "အသက်ရှူခက်နေတယ်", mustLock: true },
  { id: "br-negated", display: "breathing is normal, no breathlessness", mustLock: false },
  // stroke_sign
  { id: "st-droop", display: "face droop started an hour ago", mustLock: true },
  { id: "st-slurred", display: "slurred speech and sudden weakness", mustLock: true },
  { id: "st-my", display: "မျက်နှာရွဲ့နေပါတယ်", mustLock: true },
  { id: "st-negated", display: "no weakness or slurred speech", mustLock: false },
  // altered_consciousness
  { id: "ac-fainted", display: "fainted twice today", mustLock: true },
  { id: "ac-seizure", display: "had a seizure", mustLock: true },
  { id: "ac-my", display: "သတိလစ်သွားခဲ့တယ်", mustLock: true },
  { id: "ac-negated", display: "never fainted, fully alert", mustLock: false },
  // severe_bleeding
  { id: "bl-vomiting-blood", display: "vomiting blood now", mustLock: true },
  { id: "bl-black-stool", display: "black stool since yesterday", mustLock: true },
  { id: "bl-my", display: "သွေးအန်နေပါတယ်", mustLock: true },
  { id: "bl-negated", display: "no blood anywhere, normal stool", mustLock: false },
  // anaphylaxis
  { id: "an-tongue-swelling", display: "tongue swelling after food", mustLock: true },
  { id: "an-throat", display: "throat swelling, hard to swallow", mustLock: true },
  { id: "an-my", display: "လည်ချောင်းဖောင်းလာပါတယ်", mustLock: true },
  // self_harm
  { id: "sh-suicidal", display: "feeling suicidal", mustLock: true },
  { id: "sh-hurt-myself", display: "I want to hurt myself", mustLock: true },
  { id: "sh-my", display: "ကိုယ့်ကိုယ်ကို သတ်ချင်နေပါတယ်", mustLock: true },
  // vital rules (must-lock)
  { id: "vt-oxygen-88", observation: { kind: "oxygen_saturation", value: { value: 88 }, unit: "percent" }, mustLock: true },
  { id: "vt-systolic-82", observation: { kind: "blood_pressure", value: { systolic: 82, diastolic: 50 }, unit: "mmHg" }, mustLock: true },
  { id: "vt-heart-rate-160", observation: { kind: "heart_rate", value: { value: 160 }, unit: "bpm" }, mustLock: true },
  { id: "vt-glucose-50", observation: { kind: "glucose", value: { value: 50 }, unit: "mg/dL" }, mustLock: true },
  // vital controls (must-NOT-lock)
  { id: "vt-oxygen-98-ok", observation: { kind: "oxygen_saturation", value: { value: 98 }, unit: "percent" }, mustLock: false },
  { id: "vt-bp-118-76-ok", observation: { kind: "blood_pressure", value: { systolic: 118, diastolic: 76 }, unit: "mmHg" }, mustLock: false },
  { id: "vt-hr-72-ok", observation: { kind: "heart_rate", value: { value: 72 }, unit: "bpm" }, mustLock: false }
];

describe("never-event corpus (CS-01)", () => {
  for (const testCase of NEVER_EVENTS) {
    it(`${testCase.mustLock ? "LOCKS" : "does NOT lock"}: ${testCase.id}`, () => {
      const overrides: Partial<KernelInput> = {};
      if (testCase.display !== undefined) {
        overrides.facts = [fact(testCase.display)];
      }
      if (testCase.observation !== undefined) {
        overrides.observations = [
          observation(testCase.observation.kind, testCase.observation.value, testCase.observation.unit)
        ];
      }
      const assessment = evaluateSafety(input(overrides));
      if (testCase.mustLock) {
        expect(assessment.urgency, `${testCase.id} failed to lock`).toBe("emergency_now");
        expect(assessment.emergencyLock, `${testCase.id} missing emergencyLock`).toBe(true);
      } else {
        expect(assessment.urgency, `${testCase.id} locked unexpectedly`).not.toBe("emergency_now");
        expect(assessment.emergencyLock).toBeFalsy();
      }
    });
  }

  it("corpus size is pinned so silent shrinkage fails loudly", () => {
    expect(NEVER_EVENTS.length).toBeGreaterThanOrEqual(30);
  });
});
