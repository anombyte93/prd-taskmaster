export interface Env {
  LICENSE_DB: D1Database;
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_API_KEY: string;
  ED25519_PRIVATE_KEY: string;
  RESEND_API_KEY: string;
}
