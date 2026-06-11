const RESEND_EMAIL_URL = "https://api.resend.com/emails";
const FROM_ADDRESS = "Atlas AI <licenses@atlas-ai.au>";
const SUPPORT_EMAIL = "support@atlas-ai.au";
const ACTIVATION_DOCS_URL = "https://atlas-ai.au/docs/activation";
const RETRY_DELAYS_MS = [1000, 2000, 4000];
const MAX_ATTEMPTS = RETRY_DELAYS_MS.length + 1;

export type LicenseEmailPlan = "pro-monthly" | "pro-annual";

type EmailFetcher = (input: string, init: RequestInit) => Promise<Response>;
type Sleep = (delayMs: number) => Promise<void>;

export interface SendLicenseEmailOptions {
  fetcher?: EmailFetcher;
  sleep?: Sleep;
  idempotencyKey?: string;
}

export class EmailDeliveryError extends Error {
  override name = "EmailDeliveryError";

  constructor(
    message: string,
    readonly attempts: number,
    readonly transient: boolean,
    readonly status?: number
  ) {
    super(message);
  }
}

function defaultSleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function planLabel(plan: LicenseEmailPlan): string {
  return plan === "pro-annual" ? "Atlas Pro Annual" : "Atlas Pro Monthly";
}

function buildEmailBody(key: string, plan: LicenseEmailPlan): { text: string; html: string } {
  const command = `script.py license-activate ${key}`;
  const pluginCommand = `/license-activate ${key}`;
  const text = [
    "Your Atlas Pro license key is ready.",
    "",
    `Plan: ${planLabel(plan)}`,
    `License key: ${key}`,
    "",
    `Activate from the CLI: ${command}`,
    `Activate from Claude Code: ${pluginCommand}`,
    `Activation docs: ${ACTIVATION_DOCS_URL}`,
    "",
    `Support: ${SUPPORT_EMAIL}`
  ].join("\n");
  const escapedKey = escapeHtml(key);
  const html = [
    "<p>Your Atlas Pro license key is ready.</p>",
    `<p><strong>Plan:</strong> ${escapeHtml(planLabel(plan))}</p>`,
    `<p><strong>License key:</strong> <code>${escapedKey}</code></p>`,
    `<p><strong>CLI:</strong> <code>script.py license-activate ${escapedKey}</code></p>`,
    `<p><strong>Claude Code:</strong> <code>/license-activate ${escapedKey}</code></p>`,
    `<p><a href="${ACTIVATION_DOCS_URL}">Activation docs</a></p>`,
    `<p>Support: <a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a></p>`
  ].join("");

  return { text, html };
}

export async function sendLicenseEmail(
  toEmail: string,
  key: string,
  plan: LicenseEmailPlan,
  resendApiKey: string,
  options: SendLicenseEmailOptions = {}
): Promise<void> {
  const fetcher: EmailFetcher = options.fetcher ?? ((input, init) => fetch(input, init));
  const sleep = options.sleep ?? defaultSleep;
  const { text, html } = buildEmailBody(key, plan);
  const headers: Record<string, string> = {
    authorization: `Bearer ${resendApiKey}`,
    "content-type": "application/json"
  };
  if (options.idempotencyKey) {
    headers["idempotency-key"] = options.idempotencyKey;
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetcher(RESEND_EMAIL_URL, {
        method: "POST",
        headers,
        body: JSON.stringify({
          from: FROM_ADDRESS,
          to: [toEmail],
          subject: "Your Atlas Pro License Key",
          text,
          html
        })
      });

      if (response.ok) {
        return;
      }

      const transient = response.status >= 500;
      if (!transient || attempt === MAX_ATTEMPTS) {
        throw new EmailDeliveryError(
          `Resend email delivery failed with HTTP ${response.status}`,
          attempt,
          transient,
          response.status
        );
      }
    } catch (error) {
      if (error instanceof EmailDeliveryError) {
        throw error;
      }
      if (attempt === MAX_ATTEMPTS) {
        throw new EmailDeliveryError("Resend email delivery failed after a network error", attempt, true);
      }
    }

    await sleep(RETRY_DELAYS_MS[attempt - 1]);
  }
}
