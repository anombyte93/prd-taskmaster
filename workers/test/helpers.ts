import { env } from "cloudflare:test";
import Stripe from "stripe";
import type { Env } from "../src/types";

export const TEST_STRIPE_WEBHOOK_SECRET = "stripe_webhook_test_secret";
export const TEST_STRIPE_API_KEY = "stripe_api_test_key";
export const TEST_PRIVATE_SEED_HEX =
  "36c0ed3c3e7c3514443c21504a2d2a3cacc661eba233a2913cb8e7bd9c089053";
export const TEST_PUBLIC_KEY_HEX =
  "1fc868c32afba550e6db6db038302a6bd83fbbd848a87191f3a03bdcccf7e88d";

export function makeTestEnv(overrides: Partial<Env> = {}): Env {
  return {
    ...env,
    STRIPE_WEBHOOK_SECRET: TEST_STRIPE_WEBHOOK_SECRET,
    STRIPE_API_KEY: TEST_STRIPE_API_KEY,
    ED25519_PRIVATE_KEY: TEST_PRIVATE_SEED_HEX,
    RESEND_API_KEY: "resend_test_key",
    ...overrides
  };
}

export async function signedStripeRequest(
  event: Record<string, unknown>,
  path = "/stripe/webhook"
): Promise<Request<unknown, IncomingRequestCfProperties>> {
  const payload = JSON.stringify(event);
  const header = await Stripe.webhooks.generateTestHeaderStringAsync({
    payload,
    secret: TEST_STRIPE_WEBHOOK_SECRET
  });

  return new Request(`https://api.atlas-ai.au${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "stripe-signature": header
    },
    body: payload
  }) as unknown as Request<unknown, IncomingRequestCfProperties>;
}

export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function b64urlDecode(value: string): Uint8Array {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export async function decodeAndVerifyAtlasKey(key: string): Promise<{
  ok: boolean;
  payload: Record<string, unknown>;
}> {
  const body = key.replace(/^ATLAS-/, "");
  const [payloadSegment, signatureSegment] = body.split(".");
  const payloadBytes = b64urlDecode(payloadSegment);
  const signature = b64urlDecode(signatureSegment);
  const publicKey = await crypto.subtle.importKey(
    "raw",
    hexToBytes(TEST_PUBLIC_KEY_HEX),
    { name: "Ed25519" },
    false,
    ["verify"]
  );
  const ok = await crypto.subtle.verify("Ed25519", publicKey, signature, payloadBytes);

  return {
    ok,
    payload: JSON.parse(new TextDecoder().decode(payloadBytes)) as Record<string, unknown>
  };
}
