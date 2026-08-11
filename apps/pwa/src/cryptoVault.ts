import { db, type EncryptedAttachmentRecord, type EncryptedEventRecord, type VaultRecord, type WrappedSecret } from "./db";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function bufferSource(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlToBytes(value: string): Uint8Array {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function randomBytes(length: number): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(length));
}

async function sha256(value: Uint8Array | string): Promise<string> {
  const bytes = typeof value === "string" ? encoder.encode(value) : value;
  return bytesToBase64Url(new Uint8Array(await crypto.subtle.digest("SHA-256", bufferSource(bytes))));
}

async function sha256Hex(value: Uint8Array | string): Promise<string> {
  const bytes = typeof value === "string" ? encoder.encode(value) : value;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bufferSource(bytes)));
  return [...digest].map((item) => item.toString(16).padStart(2, "0")).join("");
}

async function wrapBytes(key: CryptoKey, cleartext: Uint8Array, aad: string): Promise<WrappedSecret> {
  const nonce = randomBytes(12);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: bufferSource(nonce), additionalData: bufferSource(encoder.encode(aad)) },
    key,
    bufferSource(cleartext)
  );
  return { ciphertext: bytesToBase64Url(new Uint8Array(ciphertext)), nonce: bytesToBase64Url(nonce) };
}

async function unwrapBytes(key: CryptoKey, wrapped: WrappedSecret, aad: string): Promise<ArrayBuffer> {
  return crypto.subtle.decrypt(
    { name: "AES-GCM", iv: bufferSource(base64UrlToBytes(wrapped.nonce)), additionalData: bufferSource(encoder.encode(aad)) },
    key,
    bufferSource(base64UrlToBytes(wrapped.ciphertext))
  );
}

async function createPasskey(profileId: string): Promise<string | undefined> {
  if (!("credentials" in navigator) || !window.PublicKeyCredential) return undefined;
  try {
    const credential = (await navigator.credentials.create({
      publicKey: {
        challenge: bufferSource(randomBytes(32)),
        rp: { name: "Personal Health Steward" },
        user: {
          id: bufferSource(randomBytes(32)),
          name: `local-${profileId.slice(0, 8)}`,
          displayName: "Local health profile"
        },
        pubKeyCredParams: [{ type: "public-key", alg: -7 }],
        authenticatorSelection: { authenticatorAttachment: "platform", userVerification: "required" },
        timeout: 60_000,
        attestation: "none"
      }
    })) as PublicKeyCredential | null;
    return credential ? bytesToBase64Url(new Uint8Array(credential.rawId)) : undefined;
  } catch {
    return undefined;
  }
}

async function assertPasskey(credentialId?: string): Promise<void> {
  if (!credentialId) return;
  const credential = await navigator.credentials.get({
    publicKey: {
      challenge: bufferSource(randomBytes(32)),
      allowCredentials: [{ id: bufferSource(base64UrlToBytes(credentialId)), type: "public-key" }],
      userVerification: "required",
      timeout: 60_000
    }
  });
  if (!credential) throw new Error("Device presence could not be verified");
}

export interface UnlockedVault {
  record: VaultRecord;
  profileKey: CryptoKey;
}

export interface InitializedVault extends UnlockedVault {
  recoveryCode: string;
  passkeyCreated: boolean;
}

export async function hasVault(): Promise<boolean> {
  return (await db.vault.get("primary")) !== undefined;
}

export async function initializeVault(): Promise<InitializedVault> {
  if (await hasVault()) throw new Error("A local vault already exists");
  const profileId = crypto.randomUUID();
  const deviceKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  const exportableProfileKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
  const rawProfileKey = new Uint8Array(await crypto.subtle.exportKey("raw", exportableProfileKey));
  const profileKey = await crypto.subtle.importKey("raw", bufferSource(rawProfileKey), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
  const recoveryRaw = randomBytes(32);
  const recoveryKey = await crypto.subtle.importKey("raw", bufferSource(recoveryRaw), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
  const wrappedProfileKey = await wrapBytes(deviceKey, rawProfileKey, `profile-device:${profileId}`);
  const recoveryWrappedProfileKey = await wrapBytes(recoveryKey, rawProfileKey, `profile-recovery:${profileId}`);
  rawProfileKey.fill(0);

  const signingKeys = (await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign", "verify"]
  )) as CryptoKeyPair;
  const signingPublicJwk = await crypto.subtle.exportKey("jwk", signingKeys.publicKey);
  const passkeyCredentialId = await createPasskey(profileId);
  const record: VaultRecord = {
    id: "primary",
    profileId,
    profilePseudonym: bytesToBase64Url(randomBytes(24)),
    deviceId: bytesToBase64Url(randomBytes(18)),
    deviceKey,
    wrappedProfileKey,
    recoveryWrappedProfileKey,
    signingPrivateKey: signingKeys.privateKey,
    signingPublicJwk,
    passkeyCredentialId,
    createdAt: new Date().toISOString()
  };
  await db.vault.add(record);
  return {
    record,
    profileKey,
    recoveryCode: bytesToBase64Url(recoveryRaw),
    passkeyCreated: Boolean(passkeyCredentialId)
  };
}

export async function unlockVault(): Promise<UnlockedVault> {
  const record = await db.vault.get("primary");
  if (!record) throw new Error("No local vault exists");
  await assertPasskey(record.passkeyCredentialId);
  const raw = await unwrapBytes(record.deviceKey, record.wrappedProfileKey, `profile-device:${record.profileId}`);
  const profileKey = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
  return { record, profileKey };
}

export async function recoverVault(recoveryCode: string): Promise<UnlockedVault> {
  const record = await db.vault.get("primary");
  if (!record) throw new Error("No encrypted vault exists on this device");
  const recoveryKey = await crypto.subtle.importKey(
    "raw",
    bufferSource(base64UrlToBytes(recoveryCode.trim())),
    { name: "AES-GCM" },
    false,
    ["decrypt"]
  );
  const raw = await unwrapBytes(recoveryKey, record.recoveryWrappedProfileKey, `profile-recovery:${record.profileId}`);
  const profileKey = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
  return { record, profileKey };
}

export interface DecryptedEvent<T = unknown> {
  eventId: string;
  sequence: number;
  eventType: string;
  occurredAt: string;
  payload: T;
  eventHash: string;
}

export async function appendEncryptedEvent(
  vault: UnlockedVault,
  eventType: string,
  payload: unknown
): Promise<EncryptedEventRecord> {
  const previous = await db.events.where("profileId").equals(vault.record.profileId).reverse().sortBy("sequence");
  const latest = previous[0];
  const sequence = (latest?.sequence ?? 0) + 1;
  const eventId = crypto.randomUUID();
  const occurredAt = new Date().toISOString();
  const aad = JSON.stringify({ profileId: vault.record.profileId, eventId, sequence, eventType, occurredAt, schema: 1 });
  const dataKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
  const dataKeyRaw = new Uint8Array(await crypto.subtle.exportKey("raw", dataKey));
  const nonce = randomBytes(12);
  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: bufferSource(nonce), additionalData: bufferSource(encoder.encode(aad)) },
    dataKey,
    bufferSource(encoder.encode(JSON.stringify(payload)))
  );
  const wrappedKey = await wrapBytes(vault.profileKey, dataKeyRaw, `event-key:${eventId}`);
  dataKeyRaw.fill(0);
  const ciphertext = bytesToBase64Url(new Uint8Array(ciphertextBuffer));
  const priorEventHash = latest?.eventHash ?? "GENESIS";
  const eventHash = await sha256Hex(`${priorEventHash}|${aad}|${ciphertext}|${wrappedKey.ciphertext}`);
  const record: EncryptedEventRecord = {
    eventId,
    profileId: vault.record.profileId,
    sequence,
    eventType,
    occurredAt,
    ciphertext,
    nonce: bytesToBase64Url(nonce),
    wrappedDataKey: wrappedKey.ciphertext,
    wrappedDataKeyNonce: wrappedKey.nonce,
    aad,
    priorEventHash,
    eventHash
  };
  await db.events.add(record);
  return record;
}

export async function decryptEvents(vault: UnlockedVault): Promise<DecryptedEvent[]> {
  const records = await db.events.where("profileId").equals(vault.record.profileId).sortBy("sequence");
  const events: DecryptedEvent[] = [];
  let priorHash = "GENESIS";
  for (const record of records) {
    if (record.priorEventHash !== priorHash) throw new Error("The local event chain is incomplete or reordered");
    const expectedHash = await sha256Hex(
      `${record.priorEventHash}|${record.aad}|${record.ciphertext}|${record.wrappedDataKey}`
    );
    if (expectedHash !== record.eventHash) throw new Error("The local event chain failed integrity verification");
    const rawDataKey = await unwrapBytes(
      vault.profileKey,
      { ciphertext: record.wrappedDataKey, nonce: record.wrappedDataKeyNonce },
      `event-key:${record.eventId}`
    );
    const dataKey = await crypto.subtle.importKey("raw", rawDataKey, { name: "AES-GCM" }, false, ["decrypt"]);
    const cleartext = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: bufferSource(base64UrlToBytes(record.nonce)),
        additionalData: bufferSource(encoder.encode(record.aad))
      },
      dataKey,
      bufferSource(base64UrlToBytes(record.ciphertext))
    );
    events.push({
      eventId: record.eventId,
      sequence: record.sequence,
      eventType: record.eventType,
      occurredAt: record.occurredAt,
      payload: JSON.parse(decoder.decode(cleartext)),
      eventHash: record.eventHash
    });
    priorHash = record.eventHash;
  }
  return events;
}

export async function encryptAttachment(vault: UnlockedVault, file: File): Promise<EncryptedAttachmentRecord> {
  const attachmentId = crypto.randomUUID();
  const bytes = new Uint8Array(await file.arrayBuffer());
  const contentHash = await sha256Hex(bytes);
  const aad = JSON.stringify({ profileId: vault.record.profileId, attachmentId, mediaType: file.type, byteLength: bytes.length });
  const dataKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
  const rawDataKey = new Uint8Array(await crypto.subtle.exportKey("raw", dataKey));
  const nonce = randomBytes(12);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: bufferSource(nonce), additionalData: bufferSource(encoder.encode(aad)) },
    dataKey,
    bufferSource(bytes)
  );
  const wrapped = await wrapBytes(vault.profileKey, rawDataKey, `attachment-key:${attachmentId}`);
  rawDataKey.fill(0);
  const record: EncryptedAttachmentRecord = {
    attachmentId,
    profileId: vault.record.profileId,
    mediaType: file.type || "application/octet-stream",
    byteLength: bytes.length,
    ciphertext: bytesToBase64Url(new Uint8Array(ciphertext)),
    nonce: bytesToBase64Url(nonce),
    wrappedDataKey: wrapped.ciphertext,
    wrappedDataKeyNonce: wrapped.nonce,
    aad,
    contentHash,
    createdAt: new Date().toISOString()
  };
  await db.attachments.add(record);
  return record;
}

export async function computeSnapshotHash(events: DecryptedEvent[]): Promise<string> {
  return sha256Hex(
    JSON.stringify(
      events.map((event) => ({ eventId: event.eventId, sequence: event.sequence, eventType: event.eventType, payload: event.payload }))
    )
  );
}

export async function makeSyncEnvelope(vault: UnlockedVault, event: EncryptedEventRecord) {
  const ciphertextHash = await sha256Hex(event.ciphertext);
  const aadHash = await sha256Hex(event.aad);
  const opaqueObjectId = (await sha256(`${vault.record.profilePseudonym}:${event.eventId}`)).slice(0, 43);
  const unsigned = {
    opaque_object_id: opaqueObjectId,
    profile_pseudonym: vault.record.profilePseudonym,
    device_id: vault.record.deviceId,
    client_sequence: event.sequence,
    ciphertext: event.ciphertext,
    nonce: event.nonce,
    aad_hash: aadHash,
    ciphertext_hash: ciphertextHash,
    created_at: event.occurredAt,
    ttl_seconds: 31_536_000,
    envelope_version: "1"
  };
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    vault.record.signingPrivateKey,
    bufferSource(encoder.encode(JSON.stringify(unsigned)))
  );
  return { ...unsigned, signature: bytesToBase64Url(new Uint8Array(signature)) };
}

export async function markEventSynced(eventId: string): Promise<void> {
  await db.events.update(eventId, { syncedAt: new Date().toISOString() });
}

export function exportRecoveryMetadata(vault: UnlockedVault) {
  return {
    profileId: vault.record.profileId,
    profilePseudonym: vault.record.profilePseudonym,
    deviceId: vault.record.deviceId,
    publicSigningKey: vault.record.signingPublicJwk,
    createdAt: vault.record.createdAt
  };
}
