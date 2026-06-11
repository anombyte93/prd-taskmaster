import { createExecutionContext, env } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { decodeAndVerifyAtlasKey, makeTestEnv } from "./helpers";

const GRACE_SECONDS = 1_209_600;

async function seedLicense(options: {
  lid: string;
  subHash?: string;
  plan?: "pro-monthly" | "pro-annual";
  subscriptionId?: string;
  expiresAt?: number;
  cancelledAt?: number | null;
}): Promise<void> {
  await env.LICENSE_DB.prepare(
    `INSERT INTO licenses (
      lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id,
      issued_at, expires_at, cancelled_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      options.lid,
      options.subHash ?? "d".repeat(64),
      options.plan ?? "pro-monthly",
      `cus_${options.lid}`,
      options.subscriptionId ?? `sub_${options.lid}`,
      1_700_000_000,
      options.expiresAt ?? 1_710_000_000,
      options.cancelledAt ?? null
    )
    .run();
}

function refreshRequest(body: unknown, method = "POST"): Request<unknown, IncomingRequestCfProperties> {
  return new Request("https://api.atlas-ai.au/license/refresh", {
    method,
    headers: { "content-type": "application/json" },
    body: method === "POST" ? JSON.stringify(body) : undefined
  }) as unknown as Request<unknown, IncomingRequestCfProperties>;
}

function mockStripeSubscription(status: string, currentPeriodEnd = 1_900_000_000) {
  return vi.fn(async (input: string | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.url;
    const headers = init?.headers as Record<string, string>;

    expect(url).toContain("https://api.stripe.com/v1/subscriptions/");
    expect(headers.authorization).toBe("Bearer stripe_api_test_key");
    return Response.json({
      id: url.split("/").at(-1),
      object: "subscription",
      status,
      current_period_end: currentPeriodEnd
    });
  });
}

describe("/license/refresh", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it.each([
    ["invalid JSON", "{not json"],
    ["missing lid", {}],
    ["non-string lid", { lid: 42 }]
  ])("returns 400 for %s", async (_name, body) => {
    const request = new Request("https://api.atlas-ai.au/license/refresh", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: typeof body === "string" ? body : JSON.stringify(body)
    }) as unknown as Request<unknown, IncomingRequestCfProperties>;

    const response = await worker.fetch(request, makeTestEnv(), createExecutionContext());

    expect(response.status).toBe(400);
    expect(response.headers.get("access-control-allow-origin")).toBe("https://atlas-ai.au");
  });

  it("returns 403 license_not_found for an unknown lid", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await worker.fetch(
      refreshRequest({ lid: "lic_missing" }),
      makeTestEnv(),
      createExecutionContext()
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ ok: false, reason: "license_not_found" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns a fresh signed key for an active subscription", async () => {
    const periodEnd = 1_901_000_000;
    await seedLicense({
      lid: "lic_refresh",
      subHash: "e".repeat(64),
      plan: "pro-annual",
      subscriptionId: "sub_refresh"
    });
    vi.stubGlobal("fetch", mockStripeSubscription("active", periodEnd));

    const response = await worker.fetch(
      refreshRequest({ lid: "lic_refresh" }),
      makeTestEnv(),
      createExecutionContext()
    );
    const body = (await response.json()) as { ok: boolean; key: string };
    const decoded = await decodeAndVerifyAtlasKey(body.key);
    const row = await env.LICENSE_DB.prepare("SELECT expires_at FROM licenses WHERE lid = ?")
      .bind("lic_refresh")
      .first<{ expires_at: number }>();

    expect(response.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(decoded.ok).toBe(true);
    expect(decoded.payload).toMatchObject({
      lid: "lic_refresh",
      sub: "e".repeat(64),
      plan: "pro-annual",
      exp: periodEnd + GRACE_SECONDS,
      v: 1
    });
    expect(row?.expires_at).toBe(periodEnd + GRACE_SECONDS);
  });

  it("short-circuits cancelled D1 rows without calling Stripe", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await seedLicense({
      lid: "lic_cancelled",
      subscriptionId: "sub_cancelled",
      cancelledAt: 1_800_000_000
    });

    const response = await worker.fetch(
      refreshRequest({ lid: "lic_cancelled" }),
      makeTestEnv(),
      createExecutionContext()
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ ok: false, reason: "subscription_cancelled" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("persists cancellation when Stripe reports an inactive subscription", async () => {
    await seedLicense({
      lid: "lic_unpaid",
      subscriptionId: "sub_unpaid",
      cancelledAt: null
    });
    vi.stubGlobal("fetch", mockStripeSubscription("unpaid"));

    const response = await worker.fetch(
      refreshRequest({ lid: "lic_unpaid" }),
      makeTestEnv(),
      createExecutionContext()
    );
    const row = await env.LICENSE_DB.prepare("SELECT cancelled_at FROM licenses WHERE lid = ?")
      .bind("lic_unpaid")
      .first<{ cancelled_at: number | null }>();

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ ok: false, reason: "subscription_cancelled" });
    expect(row?.cancelled_at).toEqual(expect.any(Number));
  });

  it("enforces a 10-per-day rate limit per lid and resets on a new UTC day", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-11T12:00:00Z"));
    await seedLicense({ lid: "lic_limited", subscriptionId: "sub_limited" });
    await seedLicense({ lid: "lic_other", subscriptionId: "sub_other" });
    const fetchMock = mockStripeSubscription("trialing", 1_902_000_000);
    vi.stubGlobal("fetch", fetchMock);

    for (let i = 0; i < 10; i += 1) {
      const response = await worker.fetch(
        refreshRequest({ lid: "lic_limited" }),
        makeTestEnv(),
        createExecutionContext()
      );
      expect(response.status).toBe(200);
    }

    const limited = await worker.fetch(
      refreshRequest({ lid: "lic_limited" }),
      makeTestEnv(),
      createExecutionContext()
    );
    const other = await worker.fetch(
      refreshRequest({ lid: "lic_other" }),
      makeTestEnv(),
      createExecutionContext()
    );
    vi.setSystemTime(new Date("2026-06-12T00:01:00Z"));
    const nextDay = await worker.fetch(
      refreshRequest({ lid: "lic_limited" }),
      makeTestEnv(),
      createExecutionContext()
    );

    expect(limited.status).toBe(429);
    await expect(limited.json()).resolves.toEqual({ ok: false, reason: "rate_limited" });
    expect(other.status).toBe(200);
    expect(nextDay.status).toBe(200);
  });

  it("handles CORS preflight and method guards", async () => {
    const options = await worker.fetch(
      refreshRequest({}, "OPTIONS"),
      makeTestEnv(),
      createExecutionContext()
    );
    const get = await worker.fetch(
      refreshRequest({}, "GET"),
      makeTestEnv(),
      createExecutionContext()
    );

    expect(options.status).toBe(204);
    expect(options.headers.get("access-control-allow-origin")).toBe("https://atlas-ai.au");
    expect(options.headers.get("access-control-allow-methods")).toContain("POST");
    expect(get.status).toBe(405);
    expect(get.headers.get("allow")).toBe("POST, OPTIONS");
  });
});
