import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  buildPossibilityMap,
  evaluateSafety,
  localize,
  type ClinicalPack,
  type Language,
  type Observation,
  type ObservationKind,
  type SafetyAssessment
} from "@ai-doctor/clinical-kernel";
import packJson from "../../../src/ai_doctor/knowledge/v3/cardiometabolic_pack.json";
import {
  appendEncryptedEvent,
  computeSnapshotHash,
  decryptEvents,
  encryptAttachment,
  exportRecoveryMetadata,
  hasVault,
  initializeVault,
  recoverVault,
  unlockVault,
  type DecryptedEvent,
  type UnlockedVault
} from "./cryptoVault";
import { db } from "./db";
import {
  getRelayConfiguration,
  enableGenericPush,
  mirrorTaskSchedules,
  requestModelContribution,
  saveRelayConfiguration,
  syncPendingEvents,
  type RelayConfiguration
} from "./relayClient";
import {
  createFact,
  EMPTY_STATE,
  replayState,
  type AppState,
  type DocumentRecord,
  type EmergencyDirectoryEntry,
  type HealthTask,
  type MedicationRecord
} from "./state";
import { COPY } from "./copy";

const PACK = packJson as ClinicalPack;
type Tab = "today" | "concern" | "measurements" | "medications" | "documents" | "timeline" | "evidence" | "privacy";



export default function App() {
  const [mode, setMode] = useState<"checking" | "setup" | "locked" | "unlocked">("checking");
  const [vault, setVault] = useState<UnlockedVault>();
  const [events, setEvents] = useState<DecryptedEvent[]>([]);
  const [state, setState] = useState<AppState>(EMPTY_STATE);
  const [snapshotHash, setSnapshotHash] = useState("0".repeat(64));
  const [tab, setTab] = useState<Tab>("today");
  const [recoveryCode, setRecoveryCode] = useState<string>();
  const [recoveryInput, setRecoveryInput] = useState("");
  const [message, setMessage] = useState("");
  const [setupAge, setSetupAge] = useState("");
  const [setupPregnancy, setSetupPregnancy] = useState<"not_applicable" | "not_pregnant">("not_applicable");
  const [setupLanguage, setSetupLanguage] = useState<Language>("my");

  useEffect(() => {
    hasVault().then((exists) => setMode(exists ? "locked" : "setup"));
  }, []);

  const language = state.profile?.preferredLanguage ?? setupLanguage;
  const copy = COPY[language];
  const assessment: SafetyAssessment | undefined = useMemo(() => {
    if (!state.profile) return undefined;
    return evaluateSafety({
      profile: state.profile,
      facts: state.facts,
      observations: state.observations,
      answeredQuestionIds: state.answeredQuestionIds,
      snapshotHash,
      pack: PACK
    });
  }, [state, snapshotHash]);
  const possibilityMap = useMemo(() => {
    if (!state.profile || !assessment) return undefined;
    return buildPossibilityMap(
      {
        profile: state.profile,
        facts: state.facts,
        observations: state.observations,
        answeredQuestionIds: state.answeredQuestionIds,
        snapshotHash,
        pack: PACK
      },
      assessment
    );
  }, [state, snapshotHash, assessment]);

  async function refresh(currentVault = vault) {
    if (!currentVault) return;
    const currentEvents = await decryptEvents(currentVault);
    setEvents(currentEvents);
    setState(replayState(currentEvents));
    setSnapshotHash(await computeSnapshotHash(currentEvents));
  }

  async function createVault() {
    const age = Number(setupAge);
    if (!Number.isFinite(age) || age < 18 || age > 130) {
      setMessage("V1 requires an adult age between 18 and 130.");
      return;
    }
    const initialized = await initializeVault();
    setVault(initialized);
    setRecoveryCode(initialized.recoveryCode);
    await appendEncryptedEvent(initialized, "profile.created", {
      profileId: initialized.record.profileId,
      ageYears: age,
      pregnancyStatus: setupPregnancy,
      preferredLanguage: setupLanguage,
      jurisdiction: "MM"
    });
    setMode("unlocked");
    await refresh(initialized);
    setMessage(initialized.passkeyCreated ? "Local passkey and encrypted record created." : "Encrypted record created; passkey was unavailable on this browser.");
  }

  async function unlock() {
    try {
      const current = await unlockVault();
      setVault(current);
      setMode("unlocked");
      await refresh(current);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not unlock the local record");
    }
  }

  async function recover() {
    try {
      const current = await recoverVault(recoveryInput);
      setVault(current);
      setMode("unlocked");
      await refresh(current);
      setMessage("Record unlocked with the recovery kit.");
    } catch {
      setMessage("Recovery failed. The code is incorrect or the encrypted record is damaged.");
    }
  }

  async function record(eventType: string, payload: unknown) {
    if (!vault) throw new Error("Vault is locked");
    await appendEncryptedEvent(vault, eventType, payload);
    await refresh(vault);
  }

  async function changeLanguage(next: Language) {
    if (mode !== "unlocked") return setSetupLanguage(next);
    await record("language.changed", { language: next });
  }

  if (mode === "checking") return <div className="center-card">Preparing the encrypted local workspace…</div>;
  if (mode === "setup") {
    return (
      <main className="setup-shell">
        <section className="setup-card">
          <Brand language={setupLanguage} />
          <div className="language-toggle"><button onClick={() => setSetupLanguage("my")}>မြန်မာ</button><button onClick={() => setSetupLanguage("en")}>English</button></div>
          <p className="notice">{COPY[setupLanguage].preclinical}</p>
          <label>Age / အသက်<input inputMode="numeric" value={setupAge} onChange={(event) => setSetupAge(event.target.value)} placeholder="18–130" /></label>
          <label>Pregnancy scope / ကိုယ်ဝန်အခြေအနေ
            <select value={setupPregnancy} onChange={(event) => setSetupPregnancy(event.target.value as typeof setupPregnancy)}>
              <option value="not_applicable">Not applicable / မသက်ဆိုင်</option>
              <option value="not_pregnant">Not pregnant / ကိုယ်ဝန်မရှိ</option>
            </select>
          </label>
          <button className="primary" onClick={createVault}>{COPY[setupLanguage].create}</button>
          {message && <p className="error">{message}</p>}
        </section>
      </main>
    );
  }
  if (mode === "locked") {
    return (
      <main className="setup-shell">
        <section className="setup-card">
          <Brand language="en" />
          <p className="notice">The health record is encrypted on this device.</p>
          <button className="primary" onClick={unlock}>Unlock with device presence</button>
          <details>
            <summary>Use recovery kit</summary>
            <label>Recovery code<input value={recoveryInput} onChange={(event) => setRecoveryInput(event.target.value)} /></label>
            <button onClick={recover}>Recover</button>
          </details>
          {message && <p className="error">{message}</p>}
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand language={language} />
        <div className="top-actions">
          <button className="ghost" onClick={() => changeLanguage(language === "my" ? "en" : "my")}>{language === "my" ? "EN" : "မြန်မာ"}</button>
          <span className="offline-dot" title="Clinical safety works offline" />
        </div>
      </header>

      <div className="preclinical-strip">{copy.preclinical}</div>
      {assessment?.emergencyLock && (
        <section className="emergency-banner" role="alert">
          <strong>{copy.emergency}</strong>
          <p>{localize(PACK, "emergency_now", language)}</p>
          {state.emergencyDirectory.map((entry) => <p key={entry.entryId}><b>{entry.label}</b> · {entry.contact} · {entry.locality}</p>)}
        </section>
      )}
      {recoveryCode && <RecoveryKit code={recoveryCode} onStored={() => setRecoveryCode(undefined)} language={language} />}
      {message && <button className="toast" onClick={() => setMessage("")}>{message}</button>}

      <main className="content">
        {tab === "today" && <Today state={state} assessment={assessment} possibilityMap={possibilityMap} language={language} record={record} />}
        {tab === "concern" && <Concern language={language} record={record} state={state} snapshotHash={snapshotHash} setMessage={setMessage} />}
        {tab === "measurements" && <Measurements state={state} record={record} language={language} />}
        {tab === "medications" && <Medications state={state} record={record} language={language} />}
        {tab === "documents" && vault && <Documents state={state} vault={vault} record={record} language={language} />}
        {tab === "timeline" && <Timeline events={events} state={state} language={language} />}
        {tab === "evidence" && <Evidence language={language} />}
        {tab === "privacy" && vault && <Privacy vault={vault} events={events} state={state} setMessage={setMessage} record={record} language={language} />}
      </main>
      <nav className="bottom-nav" aria-label="Primary navigation">
        {(["today", "concern", "measurements", "medications", "documents", "timeline", "evidence", "privacy"] as Tab[]).map((item) => (
          <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{copy[item]}</button>
        ))}
      </nav>
    </div>
  );
}

function Brand({ language }: { language: Language }) {
  return <div className="brand"><div className="brand-mark">H</div><div><h1>{COPY[language].title}</h1><p>{COPY[language].subtitle}</p></div></div>;
}

function RecoveryKit({ code, onStored, language }: { code: string; onStored: () => void; language: Language }) {
  return <section className="recovery-card"><div><strong>{COPY[language].recovery}</strong><p>Store this offline. The server cannot recover it.</p><code>{code}</code></div><button onClick={onStored}>I stored it offline</button></section>;
}

function Today({ state, assessment, possibilityMap, language, record }: any) {
  const copy = COPY[language as Language];
  return <div className="stack">
    <section className={`status-card ${assessment?.emergencyLock ? "danger" : ""}`}>
      <span className="eyebrow">Safety status</span>
      <h2>{assessment?.emergencyLock ? copy.emergency : assessment?.urgency === "self_care_possible" ? copy.checked : copy.incomplete}</h2>
      <p>{assessment ? PACK.coverage[language as Language] : "No assessment yet."}</p>
      {assessment?.missingInputs?.length > 0 && <div className="chips">{assessment.missingInputs.map((item: string) => <span key={item}>{item}</span>)}</div>}
    </section>
    <section className="card">
      <div className="section-heading"><div><span className="eyebrow">Open loop</span><h2>Tasks and check-ins</h2></div><span className="count">{state.tasks.filter((task: HealthTask) => !["completed", "cancelled", "expired"].includes(task.status)).length}</span></div>
      {state.tasks.length === 0 ? <p className="muted">No scheduled tasks. No clinician is waiting for a response.</p> : state.tasks.map((task: HealthTask) => <TaskRow key={task.taskId} task={task} record={record} />)}
      <TaskForm record={record} />
    </section>
    <section className="card">
      <span className="eyebrow">{copy.possibilities}</span>
      <h2>{copy.notDiagnosis}</h2>
      {!possibilityMap?.hypotheses.length ? <p className="muted">A possibility map appears only after required safety information is complete.</p> : possibilityMap.hypotheses.map((item: any) => <article className="possibility" key={item.hypothesisId}><h3>{language === "my" ? item.labelMy : item.labelEn}</h3><p>Missing discriminators: {item.missingQuestionIds.join(", ")}</p><span>Unresolved · never a confirmed diagnosis</span></article>)}
    </section>
  </div>;
}

function Concern({ language, record, state, snapshotHash, setMessage }: any) {
  const [concern, setConcern] = useState("");
  const [answers, setAnswers] = useState<Record<string, "yes" | "no" | "">>({ q_chest_pain: "", q_breathing: "", q_neurologic: "" });
  const [consent, setConsent] = useState(false);
  const [modelStatus, setModelStatus] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!concern.trim() || Object.values(answers).some((value) => !value)) return setMessage("Complete the concern and all three safety questions.");
    await record("fact.recorded", createFact("symptom", concern.trim(), { text: concern.trim() }));
    const answerFacts: Record<string, [string, string]> = {
      q_chest_pain: ["chest pain now", "no chest pain"],
      q_breathing: ["difficulty breathing now", "no difficulty breathing"],
      q_neurologic: ["sudden one-sided weakness or speech difficulty", "no sudden one-sided weakness or speech difficulty"]
    };
    for (const [questionId, answer] of Object.entries(answers)) {
      await record("workup.question.answered", { questionId, answer, fact: createFact("symptom", answerFacts[questionId][answer === "yes" ? 0 : 1]) });
    }
    setConcern("");
    setMessage("Concern saved. The deterministic safety screen was rerun.");
  }
  async function runModel() {
    if (!consent) return;
    try {
      const config = await getRelayConfiguration();
      const result = await requestModelContribution(config, snapshotHash, state.facts, "configured-home-broker", "qualified-model-only");
      setModelStatus(result.abstention_reason ?? `Model contribution: ${result.validation_status}`);
    } catch (error) {
      setModelStatus(error instanceof Error ? error.message : "Model request failed safely");
    }
  }
  return <div className="stack"><section className="card"><span className="eyebrow">Guided intake</span><h2>{language === "my" ? "ဘာတွေဖြစ်နေပါသလဲ။" : "What is happening?"}</h2><form onSubmit={submit} className="form-stack"><label>Concern / အခြေအနေ<textarea value={concern} onChange={(event) => setConcern(event.target.value)} maxLength={1000} rows={4} /></label>{PACK.question_catalog.filter((item) => item.safety_critical).map((question) => <fieldset key={question.id}><legend>{question[language as Language]}</legend><label><input type="radio" name={question.id} checked={answers[question.id] === "yes"} onChange={() => setAnswers({ ...answers, [question.id]: "yes" })} /> Yes / ရှိ</label><label><input type="radio" name={question.id} checked={answers[question.id] === "no"} onChange={() => setAnswers({ ...answers, [question.id]: "no" })} /> No / မရှိ</label></fieldset>)}<button className="primary" type="submit">Save and reassess</button></form></section><section className="card"><span className="eyebrow">Optional language engine</span><h2>Per-workup consent</h2><p>Only coded symptoms and verification states will be sent. No documents, contacts, profile ID, or full history.</p><label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I consent to this one minimized reasoning request.</label><button disabled={!consent || state.facts.length === 0} onClick={runModel}>Request bounded contribution</button>{modelStatus && <p className="notice">{modelStatus}</p>}</section></div>;
}

function Measurements({ state, record, language }: any) {
  const [kind, setKind] = useState<ObservationKind>("blood_pressure");
  const [value, setValue] = useState("");
  const [second, setSecond] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const rawValue: Record<string, number> = kind === "blood_pressure" ? { systolic: Number(value), diastolic: Number(second) } : { value: Number(value) };
    const units: Record<ObservationKind, string> = { heart_rate: "bpm", blood_pressure: "mmHg", oxygen_saturation: "percent", temperature: "C", glucose: "mg/dL", weight: "kg", respiratory_rate: "breaths/min", symptom_score: "0-10" };
    const observation: Observation = { observationId: crypto.randomUUID(), kind, rawValue, rawUnit: units[kind], measuredAt: new Date().toISOString(), enteredAt: new Date().toISOString(), quality: "accepted", entryMethod: "manual" };
    await record("observation.recorded", observation);
    setValue(""); setSecond("");
  }
  return <div className="stack"><section className="card"><span className="eyebrow">Home vital capture</span><h2>{language === "my" ? "တိုင်းတာချက်အသစ်" : "New measurement"}</h2><form className="measurement-form" onSubmit={submit}><select value={kind} onChange={(event) => setKind(event.target.value as ObservationKind)}>{["blood_pressure", "heart_rate", "oxygen_saturation", "temperature", "glucose", "weight", "respiratory_rate"].map((item) => <option key={item}>{item}</option>)}</select><input required inputMode="decimal" value={value} onChange={(event) => setValue(event.target.value)} placeholder={kind === "blood_pressure" ? "Systolic" : "Value"} />{kind === "blood_pressure" && <input required inputMode="decimal" value={second} onChange={(event) => setSecond(event.target.value)} placeholder="Diastolic" />}<button className="primary">Record</button></form><p className="muted">The app checks data quality and configured danger signals. It does not declare a reading “safe” or diagnose its cause.</p></section><section className="card"><h2>History</h2><div className="table-list">{[...state.observations].reverse().map((item: Observation) => <div key={item.observationId}><b>{item.kind}</b><span>{Object.values(item.rawValue).join(" / ")} {item.rawUnit}</span><time>{new Date(item.measuredAt).toLocaleString()}</time></div>)}</div></section></div>;
}

function Medications({ state, record, language }: any) {
  const [name, setName] = useState(""); const [dose, setDose] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); const item: MedicationRecord = { medicationEntryId: crypto.randomUUID(), displayName: name, doseText: dose || undefined, reportedStatus: "taking", verificationStatus: "patient_reported", sourceKind: "person_entered", createdAt: new Date().toISOString() }; await record("medication.recorded", item); setName(""); setDose(""); }
  return <div className="stack"><section className="card"><span className="eyebrow">Personal inventory</span><h2>{language === "my" ? "ဆေးဝါးမှတ်တမ်း" : "Medication record"}</h2><form className="measurement-form" onSubmit={submit}><input required value={name} onChange={(event) => setName(event.target.value)} placeholder="Exact package name" /><input value={dose} onChange={(event) => setDose(event.target.value)} placeholder="Exact dose text (optional)" /><button className="primary">Add</button></form><p className="notice">Entries are patient-reported. The app does not tell you to start, stop, or change a medicine.</p></section><section className="card"><div className="table-list">{state.medications.map((item: MedicationRecord) => <div key={item.medicationEntryId}><b>{item.displayName}</b><span>{item.doseText || "Dose not recorded"}</span><time>{item.verificationStatus}</time></div>)}</div></section></div>;
}

function Documents({ state, vault, record, language }: any) {
  const [busy, setBusy] = useState(false);
  async function add(file?: File) { if (!file) return; setBusy(true); try { const encrypted = await encryptAttachment(vault, file); const kind: DocumentRecord["kind"] = file.type === "application/pdf" ? "pdf" : "photo"; const document: DocumentRecord = { documentId: crypto.randomUUID(), attachmentId: encrypted.attachmentId, mediaType: encrypted.mediaType, byteLength: encrypted.byteLength, contentHash: encrypted.contentHash, kind, extractionStatus: "not_processed", capturedAt: encrypted.createdAt }; await record("document.added", document); } finally { setBusy(false); } }
  return <div className="stack"><section className="card"><span className="eyebrow">Local encrypted capture</span><h2>{language === "my" ? "စာရွက်စာတမ်း ထည့်ရန်" : "Add a document"}</h2><input type="file" accept="application/pdf,image/png,image/jpeg" disabled={busy} onChange={(event) => add(event.target.files?.[0])} /><p className="muted">Files remain encrypted on this device. Extracted claims cannot affect a workup until you confirm them. Diagnostic image analysis is disabled.</p></section><section className="card"><div className="table-list">{state.documents.map((item: DocumentRecord) => <div key={item.documentId}><b>{item.kind}</b><span>{Math.round(item.byteLength / 1024)} KB · {item.extractionStatus}</span><time>{new Date(item.capturedAt).toLocaleString()}</time></div>)}</div></section></div>;
}

function Timeline({ events, state, language }: any) {
  return <section className="card"><span className="eyebrow">Append-only patient ledger</span><h2>{language === "my" ? "အချိန်လိုက်မှတ်တမ်း" : "Longitudinal timeline"}</h2><p>{events.length} encrypted, integrity-chained events · {state.facts.length} fact revisions</p><ol className="timeline">{[...events].reverse().map((event: DecryptedEvent) => <li key={event.eventId}><span>{event.sequence}</span><div><b>{event.eventType}</b><time>{new Date(event.occurredAt).toLocaleString()}</time></div></li>)}</ol></section>;
}

function Evidence({ language }: { language: Language }) {
  return <div className="stack"><section className="card"><span className="eyebrow">Signed offline pack</span><h2>{PACK.pack_id}</h2><p>{PACK.coverage[language]}</p><div className="chips"><span>{PACK.release}</span><span>Myanmar</span><span>Adult</span><span>Not clinically approved</span></div></section>{PACK.evidence.map((item) => <article className="card" key={item.id}><span className="eyebrow">{item.jurisdiction} · {item.version}</span><h3>{item.title}</h3><a href={item.uri} target="_blank" rel="noreferrer">Open source</a></article>)}</div>;
}

function Privacy({ vault, events, state, setMessage, record, language }: any) {
  const [config, setConfig] = useState<RelayConfiguration>({ baseUrl: "", token: "", vapidPublicKey: "" });
  const [directory, setDirectory] = useState<EmergencyDirectoryEntry[]>(state.emergencyDirectory);
  useEffect(() => { getRelayConfiguration().then(setConfig); }, []);
  async function saveConfig(event: FormEvent) { event.preventDefault(); await saveRelayConfiguration(config); setMessage("Private relay settings saved locally."); }
  async function sync() { try { const count = await syncPendingEvents(vault, config); setMessage(`${count} encrypted event(s) synchronized. No clinical plaintext was sent.`); } catch (error) { setMessage(error instanceof Error ? error.message : "Encrypted sync failed"); } }
  async function enablePush() { try { await enableGenericPush(vault, config); setMessage("Generic Web Push enabled. Delivery is not guaranteed and no clinical text is sent."); } catch (error) { setMessage(error instanceof Error ? error.message : "Push setup failed"); } }
  async function mirrorTasks() { try { const count = await mirrorTaskSchedules(vault, config, state.tasks); setMessage(`${count} opaque reminder schedule(s) mirrored to the home relay.`); } catch (error) { setMessage(error instanceof Error ? error.message : "Reminder mirroring failed"); } }
  async function saveDirectory(event: FormEvent) { event.preventDefault(); await record("emergency.directory.updated", { entries: directory.filter((item) => item.label && item.contact) }); setMessage("Emergency directory updated. The app does not verify or contact these services."); }
  function addDirectory() { setDirectory([...directory, { entryId: crypto.randomUUID(), label: "", contact: "", locality: "", verifiedAt: new Date().toISOString() }]); }
  function exportRecord() { const blob = new Blob([JSON.stringify({ metadata: exportRecoveryMetadata(vault), encryptedEvents: events.map((event: DecryptedEvent) => ({ eventId: event.eventId, sequence: event.sequence, eventType: event.eventType, occurredAt: event.occurredAt, eventHash: event.eventHash })) }, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "health-steward-audit-export.json"; link.click(); URL.revokeObjectURL(url); }
  return <div className="stack"><section className="card"><span className="eyebrow">Local vault</span><h2>{language === "my" ? "လုံခြုံရေးနှင့် ပြန်လည်ရယူခြင်း" : "Security and recovery"}</h2><dl><dt>Profile</dt><dd>{vault.record.profileId.slice(0, 8)}…</dd><dt>Device</dt><dd>{vault.record.deviceId.slice(0, 12)}…</dd><dt>Passkey</dt><dd>{vault.record.passkeyCredentialId ? "Enabled" : "Unavailable on this browser"}</dd><dt>Events</dt><dd>{events.length}</dd></dl><button onClick={exportRecord}>Export non-clinical audit metadata</button></section><section className="card"><h2>Home relay</h2><form className="form-stack" onSubmit={saveConfig}><label>Private HTTPS URL<input value={config.baseUrl} onChange={(event) => setConfig({ ...config, baseUrl: event.target.value })} /></label><label>Patient token<input type="password" value={config.token} onChange={(event) => setConfig({ ...config, token: event.target.value })} /></label><label>Web Push VAPID public key<input value={config.vapidPublicKey || ""} onChange={(event) => setConfig({ ...config, vapidPublicKey: event.target.value })} /></label><button>Save relay settings</button><button className="primary" type="button" onClick={sync}>{COPY[language as Language].sync}</button><button type="button" onClick={enablePush}>Enable generic Web Push</button><button type="button" onClick={mirrorTasks}>Mirror active reminder schedules</button></form><p className="muted">The relay receives ciphertext, opaque IDs, timing metadata, and generic reminder schedules only.</p></section><section className="card"><h2>Local emergency directory</h2><form className="form-stack" onSubmit={saveDirectory}>{directory.map((entry, index) => <div className="directory-row" key={entry.entryId}><input placeholder="Facility or service" value={entry.label} onChange={(event) => { const next = [...directory]; next[index] = { ...entry, label: event.target.value }; setDirectory(next); }} /><input placeholder="Phone / directions" value={entry.contact} onChange={(event) => { const next = [...directory]; next[index] = { ...entry, contact: event.target.value }; setDirectory(next); }} /><input placeholder="Locality" value={entry.locality} onChange={(event) => { const next = [...directory]; next[index] = { ...entry, locality: event.target.value }; setDirectory(next); }} /></div>)}<button type="button" onClick={addDirectory}>Add entry</button><button className="primary">Save directory</button></form></section></div>;
}

function TaskForm({ record }: { record: (type: string, payload: unknown) => Promise<void> }) {
  const [title, setTitle] = useState(""); const [dueAt, setDueAt] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); const due = new Date(dueAt); const task: HealthTask = { taskId: crypto.randomUUID(), taskType: "symptom_checkin", title, dueAt: due.toISOString(), expiresAt: new Date(due.getTime() + 7 * 86400000).toISOString(), status: "scheduled", disclaimerKey: "no_clinician_monitoring_v1" }; await record("task.created", task); setTitle(""); setDueAt(""); }
  return <form className="task-form" onSubmit={submit}><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Personal reminder" /><input required type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /><button>Add</button></form>;
}

function TaskRow({ task, record }: { task: HealthTask; record: (type: string, payload: unknown) => Promise<void> }) {
  return <div className="task-row"><div><b>{task.title}</b><span>{task.status} · {new Date(task.dueAt).toLocaleString()}</span></div>{!["completed", "cancelled", "expired"].includes(task.status) && <button onClick={() => record("task.transitioned", { taskId: task.taskId, status: "completed" })}>Done</button>}</div>;
}
