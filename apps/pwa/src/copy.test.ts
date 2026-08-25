import { describe, expect, it } from "vitest";
import { COPY, type CopyKey } from "./copy";

describe("bilingual copy parity (R4.1)", () => {
  it("has identical key sets for my and en", () => {
    const enKeys = Object.keys(COPY.en).sort();
    const myKeys = Object.keys(COPY.my).sort();
    expect(myKeys).toEqual(enKeys);
  });

  it("has no empty or whitespace-only strings in either locale", () => {
    for (const key of Object.keys(COPY) as Array<keyof typeof COPY>) {
      for (const [k, v] of Object.entries(COPY[key])) {
        expect(v.trim().length, `${key}.${k}`).toBeGreaterThan(0);
      }
    }
  });

  it("keeps Burmese strings actually Burmese where the English has prose", () => {
    // Guards against a copy-paste of the English value into the my locale.
    const proseKeys: CopyKey[] = [
      "title",
      "preclinical",
      "unlock",
      "create",
      "recovery",
      "emergency",
      "notDiagnosis",
    ];
    const burmese = /[\u1000-\u109F]/;
    for (const key of proseKeys) {
      expect(burmese.test(COPY.my[key]), `my.${key} lacks Burmese script`).toBe(true);
    }
    expect(burmese.test(COPY.en.title)).toBe(false);
  });
});
