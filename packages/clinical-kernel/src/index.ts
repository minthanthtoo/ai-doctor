export type Language = "my" | "en";
export type PregnancyStatus = "not_pregnant" | "not_applicable" | "possibly_pregnant" | "pregnant" | "unknown";
export type Urgency =
  | "emergency_now"
  | "urgent_same_day"
  | "in_person_24_48h"
  | "self_care_possible"
  | "insufficient_data"
  | "out_of_scope";

export type CoverageState =
  | "evaluated"
  | "not_assessed_missing_input"
  | "not_assessed_quality_failure"
  | "stale"
  | "conflicted"
  | "out_of_scope"
  | "release_unavailable";

export interface LocalProfile {
  profileId: string;
  ageYears?: number;
  pregnancyStatus: PregnancyStatus;
  preferredLanguage: Language;
  jurisdiction: "MM";
}

export interface ClinicalFact {
  factId: string;
  revisionId: string;
  kind: "symptom" | "vital" | "medication" | "allergy" | "condition" | "document_claim" | "user_note";
  display: string;
  value: Record<string, unknown>;
  verification:
    | "user_reported"
    | "device_observed"
    | "document_extracted_candidate"
    | "user_confirmed"
    | "conflicted"
    | "superseded"
    | "retracted";
  effectiveFrom?: string;
  recordedAt: string;
  supersedesRevisionId?: string;
  conflictGroupId?: string;
}

export type ObservationKind =
  | "heart_rate"
  | "blood_pressure"
  | "oxygen_saturation"
  | "temperature"
  | "glucose"
  | "weight"
  | "respiratory_rate"
  | "symptom_score";

export interface Observation {
  observationId: string;
  kind: ObservationKind;
  rawValue: Record<string, number>;
  rawUnit: string;
  measuredAt: string;
  enteredAt: string;
  quality: "accepted" | "implausible" | "incomplete" | "stale" | "duplicate";
  entryMethod: "manual" | "csv" | "connected_device";
}

export interface RedFlagRule {
  id: string;
  terms: string[];
  content_id: string;
}

export interface VitalRule {
  id: string;
  kind: ObservationKind;
  field: string;
  operator: "lt" | "lte" | "gt" | "gte";
  threshold: number;
  unit: string;
  urgency: Urgency;
  content_id: string;
}

export interface ClinicalPack {
  pack_id: string;
  release: string;
  jurisdiction: string;
  approved_for_clinical_use: boolean;
  coverage: Record<Language, string>;
  content: Record<string, Record<Language, string>>;
  red_flag_symptoms: RedFlagRule[];
  vital_rules: VitalRule[];
  required_profile_fields: string[];
  question_catalog: Array<{ id: string; en: string; my: string; safety_critical: boolean }>;
  terminology: Array<{ id: string; en: string; my: string }>;
  evidence: Array<{ id: string; title: string; uri: string; jurisdiction: string; version: string }>;
}

export interface SafetyFinding {
  ruleId: string;
  factIds: string[];
  observationIds: string[];
  contentId: string;
}

export interface SafetyAssessment {
  assessmentId: string;
  snapshotHash: string;
  urgency: Urgency;
  coverage: CoverageState;
  findings: SafetyFinding[];
  missingInputs: string[];
  staleInputs: string[];
  conflictGroupIds: string[];
  emergencyLock: boolean;
  instructionContentId?: string;
  ruleRelease: string;
  generatedAt: string;
  approvedForClinicalUse: false;
}

export interface HypothesisCandidate {
  hypothesisId: string;
  terminologyId: string;
  labelMy: string;
  labelEn: string;
  status: "active" | "less_supported" | "unresolved" | "not_assessable";
  dangerousIfMissed: boolean;
  supportFactIds: string[];
  contradictingFactIds: string[];
  missingQuestionIds: string[];
  evidenceIds: string[];
  sourceRelease: string;
  neverConfirmedAsDiagnosis: true;
}

export interface PossibilityMap {
  snapshotHash: string;
  hypotheses: HypothesisCandidate[];
  dangerousAlternatives: HypothesisCandidate[];
  limitationsContentId: "possibility_disclaimer";
  authoritative: false;
}

export interface KernelInput {
  profile: LocalProfile;
  facts: ClinicalFact[];
  observations: Observation[];
  answeredQuestionIds: string[];
  snapshotHash: string;
  pack: ClinicalPack;
}

const ENGLISH_NEGATION = /(?:\bno|\bdenies|\bdenied|\bwithout|\bnot experiencing|\bnegative for)\s+$/i;

function containsAffirmedTerm(text: string, term: string): boolean {
  const normalized = text.toLocaleLowerCase();
  const needle = term.toLocaleLowerCase();
  let index = normalized.indexOf(needle);
  while (index >= 0) {
    const prefix = normalized.slice(Math.max(0, index - 40), index).split(/[.;!?\n]/).pop() ?? "";
    const suffix = normalized.slice(index + needle.length, index + needle.length + 12);
    if (!ENGLISH_NEGATION.test(prefix) && !suffix.includes("မရှိ")) return true;
    index = normalized.indexOf(needle, index + needle.length);
  }
  return false;
}

function compare(value: number, operator: VitalRule["operator"], threshold: number): boolean {
  if (operator === "lt") return value < threshold;
  if (operator === "lte") return value <= threshold;
  if (operator === "gt") return value > threshold;
  return value >= threshold;
}

const PLAUSIBLE_RANGES: Record<ObservationKind, Record<string, [number, number]>> = {
  heart_rate: { value: [0, 350] },
  blood_pressure: { systolic: [0, 350], diastolic: [0, 250] },
  oxygen_saturation: { value: [0, 100] },
  temperature: { value: [25, 45] },
  glucose: { value: [0, 3000] },
  weight: { value: [0.2, 600] },
  respiratory_rate: { value: [0, 100] },
  symptom_score: { value: [0, 10] }
};

export function assessObservationQuality(observation: Observation): Observation["quality"] {
  if (!observation.measuredAt || Object.keys(observation.rawValue).length === 0) return "incomplete";
  const ageMs = Date.now() - new Date(observation.measuredAt).getTime();
  if (!Number.isFinite(ageMs)) return "incomplete";
  if (ageMs > 30 * 24 * 60 * 60 * 1000) return "stale";
  const ranges = PLAUSIBLE_RANGES[observation.kind];
  for (const [field, [minimum, maximum]] of Object.entries(ranges)) {
    const value = observation.rawValue[field];
    if (value === undefined || !Number.isFinite(value)) return "incomplete";
    if (value < minimum || value > maximum) return "implausible";
  }
  return observation.quality === "duplicate" ? "duplicate" : "accepted";
}

export function evaluateSafety(input: KernelInput): SafetyAssessment {
  const { profile, pack } = input;
  const activeFacts = input.facts.filter(
    (fact) => !["retracted", "superseded", "document_extracted_candidate"].includes(fact.verification)
  );
  const findings: SafetyFinding[] = [];
  const missingInputs: string[] = [];
  const staleInputs: string[] = [];
  const conflicts = activeFacts
    .filter((fact) => fact.verification === "conflicted" && fact.conflictGroupId)
    .map((fact) => fact.conflictGroupId as string);

  for (const rule of pack.red_flag_symptoms) {
    const matched = activeFacts.filter(
      (fact) =>
        (fact.kind === "symptom" || fact.kind === "user_note") &&
        rule.terms.some((term) => containsAffirmedTerm(`${fact.display} ${String(fact.value.text ?? "")}`, term))
    );
    if (matched.length) {
      findings.push({
        ruleId: rule.id,
        factIds: matched.map((fact) => fact.factId),
        observationIds: [],
        contentId: rule.content_id
      });
    }
  }

  const latestByKind = new Map<ObservationKind, Observation>();
  for (const observation of input.observations) {
    const current = latestByKind.get(observation.kind);
    if (!current || new Date(current.measuredAt) < new Date(observation.measuredAt)) {
      latestByKind.set(observation.kind, observation);
    }
  }
  for (const [kind, observation] of latestByKind) {
    const quality = assessObservationQuality(observation);
    if (quality === "stale") staleInputs.push(kind);
    if (quality !== "accepted") continue;
    for (const rule of pack.vital_rules.filter((item) => item.kind === kind)) {
      const value = observation.rawValue[rule.field];
      if (value !== undefined && compare(value, rule.operator, rule.threshold)) {
        findings.push({
          ruleId: rule.id,
          factIds: [],
          observationIds: [observation.observationId],
          contentId: rule.content_id
        });
      }
    }
  }

  if (findings.length) {
    return {
      assessmentId: crypto.randomUUID(),
      snapshotHash: input.snapshotHash,
      urgency: "emergency_now",
      coverage: "evaluated",
      findings,
      missingInputs,
      staleInputs,
      conflictGroupIds: conflicts,
      emergencyLock: true,
      instructionContentId: "emergency_now",
      ruleRelease: pack.release,
      generatedAt: new Date().toISOString(),
      approvedForClinicalUse: false
    };
  }

  if (profile.ageYears === undefined) missingInputs.push("age_years");
  if (profile.pregnancyStatus === "unknown") missingInputs.push("pregnancy_status");
  if (profile.ageYears !== undefined && profile.ageYears < 18) {
    return baseAssessment(input, "out_of_scope", "out_of_scope", missingInputs, staleInputs, conflicts);
  }
  if (profile.pregnancyStatus === "pregnant" || profile.pregnancyStatus === "possibly_pregnant") {
    return baseAssessment(input, "out_of_scope", "out_of_scope", missingInputs, staleInputs, conflicts);
  }
  if (conflicts.length) {
    return baseAssessment(input, "insufficient_data", "conflicted", missingInputs, staleInputs, conflicts);
  }
  if (staleInputs.length) {
    return baseAssessment(input, "insufficient_data", "stale", missingInputs, staleInputs, conflicts);
  }
  if (!activeFacts.length && !input.observations.length) missingInputs.push("current_concern_or_observation");
  const safetyQuestions = pack.question_catalog.filter((question) => question.safety_critical).map((item) => item.id);
  const unansweredSafetyQuestions = safetyQuestions.filter((id) => !input.answeredQuestionIds.includes(id));
  missingInputs.push(...unansweredSafetyQuestions);
  if (missingInputs.length) {
    return baseAssessment(
      input,
      "insufficient_data",
      "not_assessed_missing_input",
      [...new Set(missingInputs)],
      staleInputs,
      conflicts
    );
  }
  return baseAssessment(input, "self_care_possible", "evaluated", [], staleInputs, conflicts);
}

function baseAssessment(
  input: KernelInput,
  urgency: Urgency,
  coverage: CoverageState,
  missingInputs: string[],
  staleInputs: string[],
  conflictGroupIds: string[]
): SafetyAssessment {
  return {
    assessmentId: crypto.randomUUID(),
    snapshotHash: input.snapshotHash,
    urgency,
    coverage,
    findings: [],
    missingInputs,
    staleInputs,
    conflictGroupIds,
    emergencyLock: false,
    instructionContentId: urgency === "insufficient_data" ? "insufficient_data" : undefined,
    ruleRelease: input.pack.release,
    generatedAt: new Date().toISOString(),
    approvedForClinicalUse: false
  };
}

export function buildPossibilityMap(input: KernelInput, assessment: SafetyAssessment): PossibilityMap {
  if (assessment.emergencyLock || assessment.urgency !== "self_care_possible") {
    return {
      snapshotHash: input.snapshotHash,
      hypotheses: [],
      dangerousAlternatives: [],
      limitationsContentId: "possibility_disclaimer",
      authoritative: false
    };
  }
  const candidates = new Map<string, { support: string[]; questions: string[] }>();
  const add = (id: string, observationId: string, questions: string[] = ["q_repeat_measurement"]) => {
    const current = candidates.get(id) ?? { support: [], questions: [] };
    current.support.push(observationId);
    current.questions.push(...questions);
    candidates.set(id, current);
  };
  for (const observation of input.observations) {
    if (assessObservationQuality(observation) !== "accepted") {
      add("possibility.measurement_issue", observation.observationId);
      continue;
    }
    if (observation.kind === "blood_pressure") add("possibility.blood_pressure_problem", observation.observationId);
    if (observation.kind === "glucose") add("possibility.glucose_problem", observation.observationId);
    if (observation.kind === "oxygen_saturation") add("possibility.oxygen_problem", observation.observationId, ["q_breathing", "q_repeat_measurement"]);
    if (observation.kind === "temperature") add("possibility.infection", observation.observationId);
    if (observation.kind === "heart_rate") add("possibility.heart_rate_response", observation.observationId);
  }
  const hypotheses = [...candidates.entries()].slice(0, 5).map(([id, details]) => {
    const term = input.pack.terminology.find((item) => item.id === id);
    if (!term) throw new Error(`Unknown terminology ID: ${id}`);
    return {
      hypothesisId: crypto.randomUUID(),
      terminologyId: id,
      labelMy: term.my,
      labelEn: term.en,
      status: "unresolved" as const,
      dangerousIfMissed: false,
      supportFactIds: details.support,
      contradictingFactIds: [],
      missingQuestionIds: [...new Set(details.questions)],
      evidenceIds: input.pack.evidence.map((item) => item.id),
      sourceRelease: input.pack.release,
      neverConfirmedAsDiagnosis: true as const
    };
  });
  return {
    snapshotHash: input.snapshotHash,
    hypotheses,
    dangerousAlternatives: [],
    limitationsContentId: "possibility_disclaimer",
    authoritative: false
  };
}

export function nextEpisodeState(assessment: SafetyAssessment, hasPossibilities: boolean): string {
  if (assessment.emergencyLock) return "emergency_lock";
  if (assessment.urgency === "urgent_same_day" || assessment.urgency === "in_person_24_48h") return "urgent_route";
  if (assessment.urgency === "insufficient_data" || assessment.urgency === "out_of_scope") return "incomplete";
  return hasPossibilities ? "possibility_map" : "collecting_workup";
}

export function localize(pack: ClinicalPack, contentId: string, language: Language): string {
  const content = pack.content[contentId];
  if (!content) throw new Error(`Unknown content ID: ${contentId}`);
  return content[language] ?? content.en;
}
