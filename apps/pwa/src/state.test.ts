import { describe, expect, it } from "vitest";
import { replayState, type HealthTask } from "./state";
import type { DecryptedEvent } from "./cryptoVault";

function event(sequence: number, eventType: string, payload: unknown): DecryptedEvent {
  return {
    eventId: crypto.randomUUID(),
    sequence,
    eventType,
    occurredAt: new Date().toISOString(),
    payload,
    eventHash: String(sequence).padStart(64, "0")
  };
}

describe("longitudinal event replay", () => {
  it("preserves fact revisions instead of overwriting them", () => {
    const factId = crypto.randomUUID();
    const state = replayState([
      event(1, "profile.created", {
        profileId: crypto.randomUUID(),
        ageYears: 42,
        pregnancyStatus: "not_applicable",
        preferredLanguage: "en",
        jurisdiction: "MM"
      }),
      event(2, "fact.recorded", {
        factId,
        revisionId: crypto.randomUUID(),
        kind: "symptom",
        display: "headache",
        value: {},
        verification: "user_reported",
        recordedAt: new Date().toISOString()
      }),
      event(3, "fact.recorded", {
        factId,
        revisionId: crypto.randomUUID(),
        kind: "symptom",
        display: "headache resolved by user report",
        value: {},
        verification: "user_confirmed",
        recordedAt: new Date().toISOString()
      })
    ]);
    expect(state.facts).toHaveLength(2);
    expect(state.facts[0].factId).toBe(state.facts[1].factId);
    expect(state.facts[0].revisionId).not.toBe(state.facts[1].revisionId);
  });

  it("does not infer task completion from silence", () => {
    const task: HealthTask = {
      taskId: crypto.randomUUID(),
      taskType: "symptom_checkin",
      title: "Check symptoms",
      dueAt: new Date(Date.now() - 60_000).toISOString(),
      expiresAt: new Date(Date.now() + 86_400_000).toISOString(),
      status: "scheduled",
      disclaimerKey: "no_clinician_monitoring_v1"
    };
    const state = replayState([event(1, "task.created", task)]);
    expect(state.tasks[0].status).toBe("due");
  });
});
