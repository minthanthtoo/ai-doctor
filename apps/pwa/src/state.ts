import type { ClinicalFact, Language, LocalProfile, Observation } from "@ai-doctor/clinical-kernel";
import type { DecryptedEvent } from "./cryptoVault";

export interface HealthTask {
  taskId: string;
  taskType: "record_vital" | "symptom_checkin" | "reconfirm_medication" | "read_education" | "contact_service";
  title: string;
  dueAt: string;
  expiresAt: string;
  status: "scheduled" | "due" | "completed" | "skipped" | "expired" | "cancelled";
  disclaimerKey: "no_clinician_monitoring_v1";
}

export interface MedicationRecord {
  medicationEntryId: string;
  displayName: string;
  doseText?: string;
  routeText?: string;
  frequencyText?: string;
  reportedStatus: "taking" | "not_taking" | "unsure" | "historical";
  verificationStatus: "patient_reported" | "unverified_candidate" | "conflicted";
  sourceKind: "person_entered" | "label_scan_candidate" | "imported_document_candidate";
  createdAt: string;
}

export interface DocumentRecord {
  documentId: string;
  attachmentId: string;
  mediaType: string;
  byteLength: number;
  contentHash: string;
  kind: "photo" | "pdf" | "lab_report" | "discharge_note" | "prescription_image";
  extractionStatus: "not_processed" | "candidate_extracted" | "rejected" | "failed";
  capturedAt: string;
}

export interface EmergencyDirectoryEntry {
  entryId: string;
  label: string;
  contact: string;
  hours?: string;
  locality?: string;
  verifiedAt: string;
}

export interface AppState {
  profile?: LocalProfile;
  facts: ClinicalFact[];
  observations: Observation[];
  answeredQuestionIds: string[];
  tasks: HealthTask[];
  medications: MedicationRecord[];
  documents: DocumentRecord[];
  emergencyDirectory: EmergencyDirectoryEntry[];
}

export const EMPTY_STATE: AppState = {
  facts: [],
  observations: [],
  answeredQuestionIds: [],
  tasks: [],
  medications: [],
  documents: [],
  emergencyDirectory: []
};

export function replayState(events: DecryptedEvent[]): AppState {
  const state: AppState = structuredClone(EMPTY_STATE);
  for (const event of events) {
    const payload = event.payload as Record<string, unknown>;
    if (event.eventType === "profile.created" || event.eventType === "profile.updated") {
      state.profile = { ...(state.profile ?? {}), ...payload } as LocalProfile;
    }
    if (event.eventType === "language.changed" && state.profile) {
      state.profile.preferredLanguage = payload.language as Language;
    }
    if (event.eventType === "fact.recorded") state.facts.push(payload as unknown as ClinicalFact);
    if (event.eventType === "observation.recorded") state.observations.push(payload as unknown as Observation);
    if (event.eventType === "workup.question.answered") {
      const questionId = payload.questionId as string;
      if (!state.answeredQuestionIds.includes(questionId)) state.answeredQuestionIds.push(questionId);
      const fact = payload.fact as ClinicalFact | undefined;
      if (fact) state.facts.push(fact);
    }
    if (event.eventType === "task.created") state.tasks.push(payload as unknown as HealthTask);
    if (event.eventType === "task.transitioned") {
      const task = state.tasks.find((item) => item.taskId === payload.taskId);
      if (task) task.status = payload.status as HealthTask["status"];
    }
    if (event.eventType === "medication.recorded") state.medications.push(payload as unknown as MedicationRecord);
    if (event.eventType === "document.added") state.documents.push(payload as unknown as DocumentRecord);
    if (event.eventType === "emergency.directory.updated") {
      state.emergencyDirectory = payload.entries as EmergencyDirectoryEntry[];
    }
  }
  const now = Date.now();
  for (const task of state.tasks) {
    if (["completed", "skipped", "cancelled"].includes(task.status)) continue;
    if (new Date(task.expiresAt).getTime() <= now) task.status = "expired";
    else if (new Date(task.dueAt).getTime() <= now) task.status = "due";
  }
  return state;
}

export function createFact(
  kind: ClinicalFact["kind"],
  display: string,
  value: Record<string, unknown> = {},
  verification: ClinicalFact["verification"] = "user_reported"
): ClinicalFact {
  return {
    factId: crypto.randomUUID(),
    revisionId: crypto.randomUUID(),
    kind,
    display,
    value,
    verification,
    recordedAt: new Date().toISOString()
  };
}
