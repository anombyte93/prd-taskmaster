import { describe, expect, it } from "vitest";
import vectors from "../../tests/license/test_vectors.json";
import { signLicensePayload } from "../src/license-signer";
import type { LicensePayload } from "../src/license-signer";
import { TEST_PRIVATE_SEED_HEX } from "./helpers";

describe("Worker license signer", () => {
  it("reproduces committed reproducible license vectors byte-for-byte", async () => {
    for (const vector of vectors.vectors) {
      if (!vector.reproducible) {
        continue;
      }

      await expect(signLicensePayload(vector.payload as LicensePayload, TEST_PRIVATE_SEED_HEX)).resolves.toBe(vector.key);
    }
  });
});
