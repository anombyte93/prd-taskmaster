import { env, SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

describe("Worker route scaffold", () => {
  it("returns 404 for unknown paths", async () => {
    const response = await SELF.fetch("https://api.atlas-ai.au/");

    expect(response.status).toBe(404);
  });

  it("exposes the LICENSE_DB D1 binding to tests", () => {
    expect(env.LICENSE_DB).toBeDefined();
    expect(typeof env.LICENSE_DB.prepare).toBe("function");
  });

  it.each(["/telemetry"])("returns 501 for POST %s until handlers are implemented", async (path) => {
    const response = await SELF.fetch(`https://api.atlas-ai.au${path}`, {
      method: "POST"
    });

    expect(response.status).toBe(501);
  });

  it.each([
    "/stripe/webhook",
    "/license/refresh",
    "/telemetry"
  ])("returns 405 for unsupported methods on %s", async (path) => {
    const response = await SELF.fetch(`https://api.atlas-ai.au${path}`, {
      method: "GET"
    });

    expect(response.status).toBe(405);
  });
});
