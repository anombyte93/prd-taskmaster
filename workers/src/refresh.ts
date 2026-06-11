import { signLicensePayload, type LicensePayload } from "./license-signer";
import type { Env } from "./types";

const LICENSE_GRACE_SECONDS = 14 * 24 * 60 * 60;
const ACTIVE_STATUSES = new Set(["active", "trialing"]);
const CORS_HEADERS = {
  "access-control-allow-origin": "https://atlas-ai.au",
  "access-control-allow-methods": "POST, OPTIONS",
  "access-control-allow-headers": "content-type"
};

interface LicenseRow {
  lid: string;
  sub_hash: string;
  plan: "pro-monthly" | "pro-annual";
  stripe_subscription_id: string | null;
  cancelled_at: number | null;
}

interface StripeSubscriptionResponse {
  id?: unknown;
  status?: unknown;
  current_period_end?: unknown;
}

function json(data: unknown, status = 200): Response {
  return Response.json(data, {
    status,
    headers: CORS_HEADERS
  });
}

function methodNotAllowed(): Response {
  return new Response("Method Not Allowed", {
    status: 405,
    headers: {
      ...CORS_HEADERS,
      Allow: "POST, OPTIONS"
    }
  });
}

function dayKey(): string {
  return new Date(Date.now()).toISOString().slice(0, 10);
}

async function readLid(request: Request): Promise<string | null> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return null;
  }

  if (
    !body ||
    typeof body !== "object" ||
    !("lid" in body) ||
    typeof body.lid !== "string" ||
    body.lid.length === 0
  ) {
    return null;
  }
  return body.lid;
}

async function consumeRateLimit(env: Env, lid: string): Promise<number> {
  const row = await env.LICENSE_DB.prepare(
    `INSERT INTO rate_limits (lid, day, count)
      VALUES (?, ?, 1)
      ON CONFLICT(lid, day) DO UPDATE SET count = count + 1
      RETURNING count`
  )
    .bind(lid, dayKey())
    .first<{ count: number }>();

  return row?.count ?? 1;
}

async function retrieveStripeSubscription(
  env: Env,
  subscriptionId: string
): Promise<{ status: string; currentPeriodEnd: number } | null> {
  const response = await fetch(
    `https://api.stripe.com/v1/subscriptions/${encodeURIComponent(subscriptionId)}`,
    {
      method: "GET",
      headers: {
        authorization: `Bearer ${env.STRIPE_API_KEY}`
      }
    }
  );

  if (!response.ok) {
    console.log("license_refresh.stripe_subscription_lookup_failed", {
      subscriptionId,
      status: response.status
    });
    return null;
  }

  const subscription = await response.json() as StripeSubscriptionResponse;
  if (
    typeof subscription.status !== "string" ||
    !Number.isInteger(subscription.current_period_end)
  ) {
    return null;
  }

  return {
    status: subscription.status,
    currentPeriodEnd: subscription.current_period_end as number
  };
}

async function findLicense(env: Env, lid: string): Promise<LicenseRow | null> {
  return env.LICENSE_DB.prepare(
    `SELECT lid, sub_hash, plan, stripe_subscription_id, cancelled_at
      FROM licenses
      WHERE lid = ?`
  )
    .bind(lid)
    .first<LicenseRow>();
}

async function markCancelled(env: Env, lid: string): Promise<void> {
  await env.LICENSE_DB.prepare("UPDATE licenses SET cancelled_at = ? WHERE lid = ?")
    .bind(Math.floor(Date.now() / 1000), lid)
    .run();
}

export async function handleLicenseRefresh(request: Request, env: Env): Promise<Response> {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }
  if (request.method !== "POST") {
    return methodNotAllowed();
  }

  const lid = await readLid(request);
  if (!lid) {
    return json({ ok: false }, 400);
  }

  const rateLimitCount = await consumeRateLimit(env, lid);
  if (rateLimitCount > 10) {
    return json({ ok: false, reason: "rate_limited" }, 429);
  }

  const license = await findLicense(env, lid);
  if (!license) {
    return json({ ok: false, reason: "license_not_found" }, 403);
  }
  if (license.cancelled_at !== null || !license.stripe_subscription_id) {
    return json({ ok: false, reason: "subscription_cancelled" }, 403);
  }

  const subscription = await retrieveStripeSubscription(env, license.stripe_subscription_id);
  if (!subscription || !ACTIVE_STATUSES.has(subscription.status)) {
    await markCancelled(env, lid);
    return json({ ok: false, reason: "subscription_cancelled" }, 403);
  }

  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = subscription.currentPeriodEnd + LICENSE_GRACE_SECONDS;
  await env.LICENSE_DB.prepare("UPDATE licenses SET expires_at = ? WHERE lid = ?")
    .bind(expiresAt, lid)
    .run();

  const payload: LicensePayload = {
    lid: license.lid,
    sub: license.sub_hash,
    plan: license.plan,
    iat: issuedAt,
    exp: expiresAt,
    v: 1
  };
  const key = await signLicensePayload(payload, env.ED25519_PRIVATE_KEY);

  return json({ ok: true, key });
}
