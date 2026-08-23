import { describe, expect, it } from "vitest";

import { canonicalJson } from "./cryptoVault";

describe("sync envelope canonicalization", () => {
  it("sorts nested object keys without changing array order", () => {
    expect(
      canonicalJson({ z: 1, device_signing_public_jwk: { y: "y", x: "x" }, a: [2, 1] })
    ).toBe('{"a":[2,1],"device_signing_public_jwk":{"x":"x","y":"y"},"z":1}');
  });

  it("uses the WebCrypto P-256 raw signature format expected by the relay", async () => {
    const keys = await crypto.subtle.generateKey(
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["sign", "verify"]
    );
    const signature = await crypto.subtle.sign(
      { name: "ECDSA", hash: "SHA-256" },
      keys.privateKey,
      new TextEncoder().encode('{"test":true}')
    );
    expect(signature.byteLength).toBe(64);
  });
});
