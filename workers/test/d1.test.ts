import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";

describe("LICENSE_DB schema", () => {
  it("stores and queries license records", async () => {
    await env.LICENSE_DB.prepare(
      `INSERT INTO licenses (
        lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id,
        issued_at, expires_at, cancelled_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        "lic_test_001",
        "a".repeat(64),
        "pro-monthly",
        "cus_test",
        "sub_test",
        1_717_200_000,
        1_719_720_000,
        null
      )
      .run();

    const row = await env.LICENSE_DB.prepare(
      "SELECT lid, sub_hash, plan, stripe_subscription_id, expires_at FROM licenses WHERE lid = ?"
    )
      .bind("lic_test_001")
      .first<{
        lid: string;
        sub_hash: string;
        plan: string;
        stripe_subscription_id: string;
        expires_at: number;
      }>();

    expect(row).toEqual({
      lid: "lic_test_001",
      sub_hash: "a".repeat(64),
      plan: "pro-monthly",
      stripe_subscription_id: "sub_test",
      expires_at: 1_719_720_000
    });
  });
});
