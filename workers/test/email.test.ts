import { afterEach, describe, expect, it, vi } from "vitest";
import { EmailDeliveryError, sendLicenseEmail } from "../src/email";

const LICENSE_KEY = "ATLAS-test.payload.signature";
const API_KEY = "resend_test_key";

function okResponse(): Response {
  return Response.json({ id: "email_test" });
}

describe("sendLicenseEmail", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts a Resend email containing the key and activation instructions", async () => {
    const fetchMock = vi.fn(async (_input: string, _init: RequestInit) => okResponse());
    const sleep = vi.fn(async () => undefined);

    await sendLicenseEmail("buyer@example.com", LICENSE_KEY, "pro-monthly", API_KEY, {
      fetcher: fetchMock,
      sleep
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(String(init?.body)) as {
      from: string;
      to: string[];
      subject: string;
      text: string;
      html: string;
    };

    expect(url).toBe("https://api.resend.com/emails");
    expect(init).toMatchObject({
      method: "POST",
      headers: {
        authorization: `Bearer ${API_KEY}`,
        "content-type": "application/json"
      }
    });
    expect(body).toMatchObject({
      from: "Atlas AI <licenses@atlas-ai.au>",
      to: ["buyer@example.com"],
      subject: "Your Atlas Pro License Key"
    });
    expect(body.text).toContain(LICENSE_KEY);
    expect(body.text).toContain(`script.py license-activate ${LICENSE_KEY}`);
    expect(body.text).toContain(`/license-activate ${LICENSE_KEY}`);
    expect(body.text).toContain("https://atlas-ai.au/docs/activation");
    expect(body.text).toContain("support@atlas-ai.au");
    expect(body.html).toContain(LICENSE_KEY);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("retries transient Resend failures with exponential backoff", async () => {
    const fetchMock = vi
      .fn(async (_input: string, _init: RequestInit) => okResponse())
      .mockResolvedValueOnce(new Response("temporary", { status: 500 }))
      .mockResolvedValueOnce(new Response("temporary", { status: 502 }))
      .mockResolvedValueOnce(okResponse());
    const sleep = vi.fn(async () => undefined);

    await sendLicenseEmail("buyer@example.com", LICENSE_KEY, "pro-annual", API_KEY, {
      fetcher: fetchMock,
      sleep
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenNthCalledWith(1, 1000);
    expect(sleep).toHaveBeenNthCalledWith(2, 2000);
  });

  it("throws a typed error after transient retries are exhausted", async () => {
    const fetchMock = vi.fn(async (_input: string, _init: RequestInit) => new Response("temporary", { status: 503 }));
    const sleep = vi.fn(async () => undefined);

    await expect(
      sendLicenseEmail("buyer@example.com", LICENSE_KEY, "pro-monthly", API_KEY, {
        fetcher: fetchMock,
        sleep
      })
    ).rejects.toMatchObject({
      name: "EmailDeliveryError",
      attempts: 4,
      transient: true,
      status: 503
    } satisfies Partial<EmailDeliveryError>);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(sleep).toHaveBeenNthCalledWith(1, 1000);
    expect(sleep).toHaveBeenNthCalledWith(2, 2000);
    expect(sleep).toHaveBeenNthCalledWith(3, 4000);
  });

  it("does not retry permanent 4xx Resend errors", async () => {
    const fetchMock = vi.fn(async (_input: string, _init: RequestInit) => new Response("unauthorized", { status: 401 }));
    const sleep = vi.fn(async () => undefined);

    await expect(
      sendLicenseEmail("buyer@example.com", LICENSE_KEY, "pro-monthly", API_KEY, {
        fetcher: fetchMock,
        sleep
      })
    ).rejects.toMatchObject({
      name: "EmailDeliveryError",
      attempts: 1,
      transient: false,
      status: 401
    } satisfies Partial<EmailDeliveryError>);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(sleep).not.toHaveBeenCalled();
  });
});
