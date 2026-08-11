import { z } from "zod";
import type { ClinicalFact } from "@ai-doctor/clinical-kernel";
import type { HealthTask } from "./state";
import { db } from "./db";
import { makeSyncEnvelope, markEventSynced, type UnlockedVault } from "./cryptoVault";

export interface RelayConfiguration {
  baseUrl: string;
  token: string;
  vapidPublicKey?: string;
}

const CandidateContributionSchema = z.object({
  run_id: z.string().uuid(),
  snapshot_hash: z.string().regex(/^[a-f0-9]{64}$/),
  hypotheses: z.array(z.unknown()).max(5),
  dangerous_alternatives: z.array(z.unknown()).max(3),
  proposed_question_ids: z.array(z.string()).max(20),
  abstention_reason: z.string().nullable().optional(),
  provider: z.string(),
  model: z.string(),
  model_release: z.string(),
  prompt_release: z.string(),
  schema_release: z.string(),
  validation_status: z.enum(["accepted", "rejected", "disabled"])
});

export async function getRelayConfiguration(): Promise<RelayConfiguration> {
  const stored = await db.preferences.get("relay");
  const value = (stored?.value ?? {}) as Partial<RelayConfiguration>;
  return {
    baseUrl: value.baseUrl ?? import.meta.env.VITE_RELAY_URL ?? "http://127.0.0.1:8000",
    token: value.token ?? import.meta.env.VITE_RELAY_TOKEN ?? "",
    vapidPublicKey: value.vapidPublicKey ?? ""
  };
}

export async function saveRelayConfiguration(configuration: RelayConfiguration): Promise<void> {
  await db.preferences.put({ key: "relay", value: configuration });
}

function headers(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

export async function syncPendingEvents(vault: UnlockedVault, configuration: RelayConfiguration) {
  const pending = await db.events
    .where("profileId")
    .equals(vault.record.profileId)
    .filter((event) => !event.syncedAt)
    .sortBy("sequence");
  let synced = 0;
  for (const event of pending) {
    const envelope = await makeSyncEnvelope(vault, event);
    const response = await fetch(
      `${configuration.baseUrl.replace(/\/$/, "")}/v1/sync/envelopes/${envelope.opaque_object_id}`,
      { method: "PUT", headers: headers(configuration.token), body: JSON.stringify(envelope) }
    );
    if (!response.ok) throw new Error(`Relay rejected encrypted event ${event.sequence}: ${response.status}`);
    await markEventSynced(event.eventId);
    synced += 1;
  }
  return synced;
}

export async function requestModelContribution(
  configuration: RelayConfiguration,
  snapshotHash: string,
  facts: ClinicalFact[],
  provider: string,
  model: string
) {
  const now = new Date();
  const expiry = new Date(now.getTime() + 30 * 60 * 1000);
  const runId = crypto.randomUUID();
  const request = {
    run_id: runId,
    task: "possibility_generation",
    consent: {
      consent_receipt_id: crypto.randomUUID(),
      purpose: "symptom_reasoning",
      provider,
      model,
      disclosed_field_classes: ["coded_symptoms", "verification_status"],
      snapshot_hash: snapshotHash,
      issued_at: now.toISOString(),
      expires_at: expiry.toISOString(),
      revoked_at: null
    },
    snapshot_hash: snapshotHash,
    prompt_release: "possibility-map-v1-preclinical",
    schema_release: "candidate-contribution-v1",
    evidence_release: "cardiometabolic-v0-preclinical",
    facts: facts.slice(-50).map((fact) => ({
      fact_id: fact.factId,
      terminology_id: fact.kind,
      value_text: fact.display.slice(0, 240),
      verification: fact.verification
    })),
    evidence: []
  };
  const response = await fetch(`${configuration.baseUrl.replace(/\/$/, "")}/v1/model/runs`, {
    method: "POST",
    headers: headers(configuration.token),
    body: JSON.stringify(request)
  });
  if (!response.ok) throw new Error(`Model broker rejected the consented request: ${response.status}`);
  return CandidateContributionSchema.parse(await response.json());
}

function urlBase64ToArrayBuffer(value: string): ArrayBuffer {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0)).buffer;
}

export async function enableGenericPush(vault: UnlockedVault, configuration: RelayConfiguration) {
  if (!configuration.vapidPublicKey) throw new Error("A VAPID public key is required");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("This browser does not support Web Push");
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notification permission was not granted");
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToArrayBuffer(configuration.vapidPublicKey)
  });
  const serialized = subscription.toJSON();
  if (!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys.auth) {
    throw new Error("Browser returned an incomplete push subscription");
  }
  const subscriptionId = crypto.randomUUID();
  const response = await fetch(`${configuration.baseUrl.replace(/\/$/, "")}/v1/push/subscriptions`, {
    method: "POST",
    headers: headers(configuration.token),
    body: JSON.stringify({
      subscription_id: subscriptionId,
      profile_pseudonym: vault.record.profilePseudonym,
      endpoint: serialized.endpoint,
      p256dh: serialized.keys.p256dh,
      auth: serialized.keys.auth
    })
  });
  if (!response.ok) throw new Error(`Relay rejected the push subscription: ${response.status}`);
  await db.preferences.put({ key: "push-subscription-id", value: subscriptionId });
  return subscriptionId;
}

export async function mirrorTaskSchedules(
  vault: UnlockedVault,
  configuration: RelayConfiguration,
  tasks: HealthTask[]
) {
  const stored = await db.preferences.get("push-subscription-id");
  const subscriptionId = stored?.value as string | undefined;
  if (!subscriptionId) throw new Error("Enable generic Web Push before mirroring reminders");
  let scheduled = 0;
  for (const task of tasks.filter((item) => ["scheduled", "due"].includes(item.status))) {
    const scheduleId = `task_${task.taskId.replace(/-/g, "")}`;
    const response = await fetch(
      `${configuration.baseUrl.replace(/\/$/, "")}/v1/push/schedules/${scheduleId}`,
      {
        method: "PUT",
        headers: headers(configuration.token),
        body: JSON.stringify({
          opaque_schedule_id: scheduleId,
          profile_pseudonym: vault.record.profilePseudonym,
          subscription_id: subscriptionId,
          due_at: task.dueAt,
          repeat_after_seconds: 86400,
          max_repeats: 2,
          expires_at: task.expiresAt
        })
      }
    );
    if (!response.ok) throw new Error(`Relay rejected a generic reminder schedule: ${response.status}`);
    scheduled += 1;
  }
  return scheduled;
}
