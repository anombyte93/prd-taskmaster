import Stripe from "stripe";
import { EmailDeliveryError, sendLicenseEmail, type LicenseEmailPlan } from "./email";
import { signLicensePayload, type LicensePayload } from "./license-signer";
import type { Env } from "./types";

const LICENSE_GRACE_SECONDS = 14 * 24 * 60 * 60;

interface StripeSubscriptionLike {
  id?: unknown;
  current_period_end?: unknown;
}

interface StripeInvoiceLike {
  subscription?: unknown;
  customer_email?: unknown;
  customer_details?: {
    email?: unknown;
  };
  period_end?: unknown;
  lines?: {
    data?: Array<{
      period?: {
        end?: unknown;
      };
    }>;
  };
}

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status });
}

function stripeClient(env: Env): Stripe {
  return new Stripe(env.STRIPE_API_KEY, {
    httpClient: Stripe.createFetchHttpClient(),
    maxNetworkRetries: 1
  });
}

function queueLicenseEmail(
  ctx: ExecutionContext,
  env: Env,
  message: { toEmail: string; key: string; plan: LicenseEmailPlan; lid: string }
): void {
  ctx.waitUntil(
    sendLicenseEmail(message.toEmail, message.key, message.plan, env.RESEND_API_KEY, {
      idempotencyKey: `license-${message.lid}`
    }).catch((error: unknown) => {
      if (error instanceof EmailDeliveryError) {
        console.error("resend.license_email.failed", {
          lid: message.lid,
          attempts: error.attempts,
          transient: error.transient,
          status: error.status,
          message: error.message
        });
        return;
      }
      console.error("resend.license_email.failed", {
        lid: message.lid,
        message: "Unexpected email delivery failure"
      });
    })
  );
}

async function verifyStripeEvent(request: Request, env: Env): Promise<Stripe.Event | null> {
  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return null;
  }

  const rawBody = await request.text();
  try {
    return await stripeClient(env).webhooks.constructEventAsync(
      rawBody,
      signature,
      env.STRIPE_WEBHOOK_SECRET,
      undefined,
      Stripe.createSubtleCryptoProvider()
    );
  } catch {
    return null;
  }
}

function objectId(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (value && typeof value === "object" && "id" in value && typeof value.id === "string") {
    return value.id;
  }
  return null;
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function subscriptionPeriodEnd(
  env: Env,
  subscriptionValue: unknown
): Promise<{ id: string; currentPeriodEnd: number } | null> {
  const id = objectId(subscriptionValue);
  if (!id) {
    return null;
  }
  const inlineSubscription = subscriptionValue as StripeSubscriptionLike;
  if (
    typeof inlineSubscription === "object" &&
    inlineSubscription !== null &&
    Number.isInteger(inlineSubscription.current_period_end)
  ) {
    return { id, currentPeriodEnd: inlineSubscription.current_period_end as number };
  }

  const subscription = await stripeClient(env).subscriptions.retrieve(id) as unknown as StripeSubscriptionLike;
  if (typeof subscription.id === "string" && Number.isInteger(subscription.current_period_end)) {
    return {
      id: subscription.id,
      currentPeriodEnd: subscription.current_period_end as number
    };
  }
  return null;
}

async function handleCheckoutSessionCompleted(
  event: Stripe.Event,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const session = event.data.object as Stripe.Checkout.Session;
  const email = session.customer_details?.email;
  const plan = session.metadata?.plan;
  const customerId = objectId(session.customer);
  const subscription = await subscriptionPeriodEnd(env, session.subscription);

  if (!email || !customerId || !subscription || (plan !== "pro-monthly" && plan !== "pro-annual")) {
    return json({ ok: false }, 400);
  }

  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = subscription.currentPeriodEnd + LICENSE_GRACE_SECONDS;
  const lid = `lic_${crypto.randomUUID()}`;
  const subHash = await sha256Hex(email.trim().toLowerCase());
  const payload: LicensePayload = {
    lid,
    sub: subHash,
    plan,
    iat: issuedAt,
    exp: expiresAt,
    v: 1
  };

  await env.LICENSE_DB.prepare(
    `INSERT INTO licenses (
      lid, sub_hash, plan, stripe_customer_id, stripe_subscription_id,
      issued_at, expires_at, cancelled_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(lid, subHash, plan, customerId, subscription.id, issuedAt, expiresAt, null)
    .run();

  const key = await signLicensePayload(payload, env.ED25519_PRIVATE_KEY);
  queueLicenseEmail(ctx, env, { toEmail: email, key, plan, lid });
  return json({ ok: true, key, lid });
}

function invoiceEmail(invoice: Stripe.Invoice): string | null {
  const invoiceLike = invoice as unknown as StripeInvoiceLike;
  if (typeof invoiceLike.customer_email === "string") {
    return invoiceLike.customer_email;
  }
  if (typeof invoiceLike.customer_details?.email === "string") {
    return invoiceLike.customer_details.email;
  }
  return null;
}

function invoicePeriodEnd(invoice: Stripe.Invoice): number | null {
  const invoiceLike = invoice as unknown as StripeInvoiceLike;
  if (Number.isInteger(invoiceLike.period_end)) {
    return invoiceLike.period_end as number;
  }
  const linePeriodEnd = invoiceLike.lines?.data?.[0]?.period?.end;
  return Number.isInteger(linePeriodEnd) ? linePeriodEnd as number : null;
}

async function handleInvoicePaid(
  event: Stripe.Event,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const invoice = event.data.object as Stripe.Invoice;
  const subscriptionId = objectId((invoice as unknown as StripeInvoiceLike).subscription);
  const periodEnd = invoicePeriodEnd(invoice);
  const email = invoiceEmail(invoice);

  if (!subscriptionId || periodEnd === null) {
    return json({ ok: false }, 400);
  }

  const license = await env.LICENSE_DB.prepare(
    "SELECT lid, sub_hash, plan FROM licenses WHERE stripe_subscription_id = ?"
  )
    .bind(subscriptionId)
    .first<{ lid: string; sub_hash: string; plan: "pro-monthly" | "pro-annual" }>();

  if (!license) {
    console.log("stripe.invoice_paid.unknown_subscription", { subscriptionId });
    return json({ ok: true, ignored: true, reason: "unknown_subscription" });
  }

  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = periodEnd + LICENSE_GRACE_SECONDS;
  await env.LICENSE_DB.prepare(
    "UPDATE licenses SET expires_at = ? WHERE stripe_subscription_id = ?"
  )
    .bind(expiresAt, subscriptionId)
    .run();

  const key = await signLicensePayload(
    {
      lid: license.lid,
      sub: license.sub_hash,
      plan: license.plan,
      iat: issuedAt,
      exp: expiresAt,
      v: 1
    },
    env.ED25519_PRIVATE_KEY
  );
  if (email) {
    queueLicenseEmail(ctx, env, { toEmail: email, key, plan: license.plan, lid: license.lid });
  } else {
    console.log("stripe.invoice_paid.email_missing", { lid: license.lid, subscriptionId });
  }

  return json({ ok: true, key, lid: license.lid });
}

async function handleSubscriptionDeleted(event: Stripe.Event, env: Env): Promise<Response> {
  const subscription = event.data.object as Stripe.Subscription;
  const subscriptionId = objectId(subscription);

  if (!subscriptionId) {
    return json({ ok: false }, 400);
  }

  const license = await env.LICENSE_DB.prepare(
    "SELECT lid FROM licenses WHERE stripe_subscription_id = ?"
  )
    .bind(subscriptionId)
    .first<{ lid: string }>();

  if (!license) {
    console.log("stripe.subscription_deleted.unknown_subscription", { subscriptionId });
    return json({ ok: true, ignored: true, reason: "unknown_subscription" });
  }

  await env.LICENSE_DB.prepare(
    "UPDATE licenses SET cancelled_at = ? WHERE stripe_subscription_id = ?"
  )
    .bind(Math.floor(Date.now() / 1000), subscriptionId)
    .run();

  return json({ ok: true, cancelled: true, lid: license.lid });
}

async function dispatchStripeEvent(
  event: Stripe.Event,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  switch (event.type) {
    case "checkout.session.completed":
      return handleCheckoutSessionCompleted(event, env, ctx);
    case "invoice.paid":
      return handleInvoicePaid(event, env, ctx);
    case "customer.subscription.deleted":
      return handleSubscriptionDeleted(event, env);
    default:
      return json({ ok: true, ignored: true });
  }
}

async function markEventProcessed(env: Env, eventId: string): Promise<boolean> {
  const result = await env.LICENSE_DB.prepare(
    "INSERT OR IGNORE INTO processed_events (event_id, processed_at) VALUES (?, ?)"
  )
    .bind(eventId, Math.floor(Date.now() / 1000))
    .run();

  return result.meta.changes === 1;
}

export async function handleStripeWebhook(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const event = await verifyStripeEvent(request, env);
  if (!event) {
    return json({ ok: false }, 400);
  }

  if (!(await markEventProcessed(env, event.id))) {
    return json({ ok: true, duplicate: true });
  }

  return dispatchStripeEvent(event, env, ctx);
}
