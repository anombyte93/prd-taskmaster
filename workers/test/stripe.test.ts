import { createExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:test";
import Stripe from "stripe";
import { describe, expect, it } from "vitest";
import worker from "../src/index";
import {
  decodeAndVerifyAtlasKey,
  makeTestEnv,
  signedStripeRequest,
  TEST_STRIPE_WEBHOOK_SECRET
} from "./helpers";

describe("Stripe webhook signature verification", () => {
  it.each([
    ["missing signature", new Headers({ "content-type": "application/json" })],
    [
      "garbled signature",
      new Headers({
        "content-type": "application/json",
        "stripe-signature": "not-a-valid-stripe-signature"
      })
    ]
  ])("rejects %s with 400", async (_name, headers) => {
    const ctx = createExecutionContext();
    const response = await worker.fetch(
      new Request("https://api.atlas-ai.au/stripe/webhook", {
        method: "POST",
        headers,
        body: JSON.stringify({ id: "evt_bad", object: "event", type: "customer.created" })
      }),
      makeTestEnv(),
      ctx
    );

    expect(response.status).toBe(400);
  });

  it("rejects a signature generated with a different secret", async () => {
    const payload = JSON.stringify({
      id: "evt_wrong_secret",
      object: "event",
      type: "customer.created",
      data: { object: { id: "cus_test", object: "customer" } }
    });
    const header = await Stripe.webhooks.generateTestHeaderStringAsync({
      payload,
      secret: `${TEST_STRIPE_WEBHOOK_SECRET}_wrong`
    });
    const ctx = createExecutionContext();

    const response = await worker.fetch(
      new Request("https://api.atlas-ai.au/stripe/webhook", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "stripe-signature": header
        },
        body: payload
      }),
      makeTestEnv(),
      ctx
    );

    expect(response.status).toBe(400);
  });

  it("accepts a valid signed event and reaches dispatch", async () => {
    const ctx = createExecutionContext();
    const request = await signedStripeRequest({
      id: "evt_signed_customer_created",
      object: "event",
      type: "customer.created",
      data: { object: { id: "cus_test", object: "customer" } }
    });

    const response = await worker.fetch(request, makeTestEnv(), ctx);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true, ignored: true });
  });
});

describe("Stripe webhook idempotency", () => {
  it("records a processed event once and treats replay as a no-op", async () => {
    const event = {
      id: "evt_replayed_customer_created",
      object: "event",
      type: "customer.created",
      data: { object: { id: "cus_test", object: "customer" } }
    };

    const first = await worker.fetch(await signedStripeRequest(event), makeTestEnv(), createExecutionContext());
    const second = await worker.fetch(await signedStripeRequest(event), makeTestEnv(), createExecutionContext());
    const row = await env.LICENSE_DB.prepare(
      "SELECT COUNT(*) AS count FROM processed_events WHERE event_id = ?"
    )
      .bind(event.id)
      .first<{ count: number }>();

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    await expect(second.json()).resolves.toEqual({ ok: true, duplicate: true });
    expect(row?.count).toBe(1);
  });
});

describe("checkout.session.completed", () => {
  it("creates a license row and returns a signed key", async () => {
    const periodEnd = 1_800_000_000;
    const request = await signedStripeRequest({
      id: "evt_checkout_completed",
      object: "event",
      type: "checkout.session.completed",
      data: {
        object: {
          id: "cs_test",
          object: "checkout.session",
          customer: "cus_test",
          customer_details: { email: "Buyer@Example.COM" },
          metadata: { plan: "pro-monthly" },
          subscription: {
            id: "sub_checkout",
            object: "subscription",
            current_period_end: periodEnd
          }
        }
      }
    });

    const response = await worker.fetch(request, makeTestEnv(), createExecutionContext());
    const body = (await response.json()) as { ok: boolean; key: string };
    const decoded = await decodeAndVerifyAtlasKey(body.key);
    const row = await env.LICENSE_DB.prepare(
      "SELECT lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id, issued_at, expires_at FROM licenses WHERE stripe_subscription_id = ?"
    )
      .bind("sub_checkout")
      .first<{
        lid: string;
        sub_hash: string;
        plan: string;
        stripe_customer_id: string;
        stripe_subscription_id: string;
        issued_at: number;
        expires_at: number;
      }>();

    expect(response.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(decoded.ok).toBe(true);
    expect(row).toMatchObject({
      plan: "pro-monthly",
      stripe_customer_id: "cus_test",
      stripe_subscription_id: "sub_checkout",
      expires_at: periodEnd + 1_209_600
    });
    expect(decoded.payload).toMatchObject({
      lid: row?.lid,
      sub: row?.sub_hash,
      plan: "pro-monthly",
      exp: periodEnd + 1_209_600,
      v: 1
    });
    expect(typeof decoded.payload.iat).toBe("number");
  });
});

describe("invoice.paid", () => {
  it("extends expiry and returns a fresh signed key for a known subscription", async () => {
    const periodEnd = 1_801_000_000;
    await env.LICENSE_DB.prepare(
      `INSERT INTO licenses (
        lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id,
        issued_at, expires_at, cancelled_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        "lic_invoice",
        "b".repeat(64),
        "pro-annual",
        "cus_invoice",
        "sub_invoice",
        1_700_000_000,
        1_710_000_000,
        null
      )
      .run();

    const response = await worker.fetch(
      await signedStripeRequest({
        id: "evt_invoice_paid",
        object: "event",
        type: "invoice.paid",
        data: {
          object: {
            id: "in_test",
            object: "invoice",
            customer: "cus_invoice",
            subscription: "sub_invoice",
            lines: { data: [{ period: { end: periodEnd } }] }
          }
        }
      }),
      makeTestEnv(),
      createExecutionContext()
    );
    const body = (await response.json()) as { ok: boolean; key: string };
    const decoded = await decodeAndVerifyAtlasKey(body.key);
    const row = await env.LICENSE_DB.prepare(
      "SELECT expires_at FROM licenses WHERE lid = ?"
    )
      .bind("lic_invoice")
      .first<{ expires_at: number }>();

    expect(response.status).toBe(200);
    expect(decoded.ok).toBe(true);
    expect(row?.expires_at).toBe(periodEnd + 1_209_600);
    expect(decoded.payload).toMatchObject({
      lid: "lic_invoice",
      sub: "b".repeat(64),
      plan: "pro-annual",
      exp: periodEnd + 1_209_600,
      v: 1
    });
  });

  it("returns 200 and leaves D1 unchanged for an unknown subscription", async () => {
    const response = await worker.fetch(
      await signedStripeRequest({
        id: "evt_invoice_unknown_subscription",
        object: "event",
        type: "invoice.paid",
        data: {
          object: {
            id: "in_unknown",
            object: "invoice",
            subscription: "sub_missing",
            lines: { data: [{ period: { end: 1_801_000_000 } }] }
          }
        }
      }),
      makeTestEnv(),
      createExecutionContext()
    );
    const row = await env.LICENSE_DB.prepare(
      "SELECT COUNT(*) AS count FROM licenses WHERE stripe_subscription_id = ?"
    )
      .bind("sub_missing")
      .first<{ count: number }>();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      ignored: true,
      reason: "unknown_subscription"
    });
    expect(row?.count).toBe(0);
  });
});

describe("customer.subscription.deleted", () => {
  it("marks a license cancelled and duplicate delivery is a no-op", async () => {
    await env.LICENSE_DB.prepare(
      `INSERT INTO licenses (
        lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id,
        issued_at, expires_at, cancelled_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        "lic_cancel",
        "c".repeat(64),
        "pro-monthly",
        "cus_cancel",
        "sub_cancel",
        1_700_000_000,
        1_900_000_000,
        null
      )
      .run();

    const event = {
      id: "evt_subscription_deleted",
      object: "event",
      type: "customer.subscription.deleted",
      data: {
        object: {
          id: "sub_cancel",
          object: "subscription",
          status: "canceled"
        }
      }
    };

    const first = await worker.fetch(
      await signedStripeRequest(event),
      makeTestEnv(),
      createExecutionContext()
    );
    const second = await worker.fetch(
      await signedStripeRequest(event),
      makeTestEnv(),
      createExecutionContext()
    );
    const row = await env.LICENSE_DB.prepare(
      "SELECT lid, plan, expires_at, cancelled_at FROM licenses WHERE lid = ?"
    )
      .bind("lic_cancel")
      .first<{ lid: string; plan: string; expires_at: number; cancelled_at: number | null }>();

    expect(first.status).toBe(200);
    await expect(first.json()).resolves.toEqual({ ok: true, cancelled: true, lid: "lic_cancel" });
    expect(second.status).toBe(200);
    await expect(second.json()).resolves.toEqual({ ok: true, duplicate: true });
    expect(row).toMatchObject({
      lid: "lic_cancel",
      plan: "pro-monthly",
      expires_at: 1_900_000_000
    });
    expect(row?.cancelled_at).toEqual(expect.any(Number));
  });
});
