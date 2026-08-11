import Dexie, { type EntityTable } from "dexie";

export interface WrappedSecret {
  ciphertext: string;
  nonce: string;
}

export interface VaultRecord {
  id: "primary";
  profileId: string;
  profilePseudonym: string;
  deviceId: string;
  deviceKey: CryptoKey;
  wrappedProfileKey: WrappedSecret;
  recoveryWrappedProfileKey: WrappedSecret;
  signingPrivateKey: CryptoKey;
  signingPublicJwk: JsonWebKey;
  passkeyCredentialId?: string;
  createdAt: string;
}

export interface EncryptedEventRecord {
  eventId: string;
  profileId: string;
  sequence: number;
  eventType: string;
  occurredAt: string;
  ciphertext: string;
  nonce: string;
  wrappedDataKey: string;
  wrappedDataKeyNonce: string;
  aad: string;
  priorEventHash: string;
  eventHash: string;
  syncedAt?: string;
}

export interface EncryptedAttachmentRecord {
  attachmentId: string;
  profileId: string;
  mediaType: string;
  byteLength: number;
  ciphertext: string;
  nonce: string;
  wrappedDataKey: string;
  wrappedDataKeyNonce: string;
  aad: string;
  contentHash: string;
  createdAt: string;
}

export interface LocalPreference {
  key: string;
  value: unknown;
}

export class StewardDatabase extends Dexie {
  vault!: EntityTable<VaultRecord, "id">;
  events!: EntityTable<EncryptedEventRecord, "eventId">;
  attachments!: EntityTable<EncryptedAttachmentRecord, "attachmentId">;
  preferences!: EntityTable<LocalPreference, "key">;

  constructor() {
    super("ai-doctor-personal-steward-v3");
    this.version(1).stores({
      vault: "id",
      events: "eventId, profileId, sequence, eventType, occurredAt, syncedAt",
      attachments: "attachmentId, profileId, createdAt",
      preferences: "key"
    });
  }
}

export const db = new StewardDatabase();
