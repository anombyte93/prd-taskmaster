import { createExecutionContext, env } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/types";
import { makeTestEnv } from "./helpers";

const VALID_EVENTS = ["install", "atlas_invoked", "reach_execute", "ship_check_ok"] as const;

function telemetryBinding(writeDataPoint = vi.fn()): AnalyticsEngineDataset {
  return { writeDataPoint } as unknown as AnalyticsEngineDataset;
}

function telemetryEnv(writeDataPoint = vi.fn(), overrides: Partial<Env> = {}): Env {
  return makeTestEnv({
    TELEMETRY: telemetryBinding(writeDataPoint),
    ...overrides
  });
}

function telemetryRequest(body: unknown, method = "POST"): Request<unknown, IncomingRequestCfProperties> {
  return new Request("https://api.atlas-ai.au/telemetry", {
    method,
    headers: { "content-type": "application/json" },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined
  }) as unknown as Request<unknown, IncomingRequestCfProperties>;
}

async function countTelemetryRows(installId: string): Promise<number> {
  const row = await env.LICENSE_DB.prepare(
    "SELECT COUNT(*) AS count FROM telemetry_events WHERE install_id = ?"
  )
    .bind(installId)
    .first<{ count: number }>();
  return row?.count ?? 0;
}

describe("/telemetry", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("can insert and select telemetry_events rows through D1", async () => {
    await env.LICENSE_DB.prepare(
      "INSERT INTO telemetry_events (install_id, event, version, os, timestamp) VALUES (?, ?, ?, ?, ?)"
    )
      .bind("install_binding", "install", "1.0.0", "linux", "2026-06-11T00:00:00.000Z")
      .run();

    await expect(countTelemetryRows("install_binding")).resolves.toBe(1);
  });

  it.each(VALID_EVENTS)("accepts valid %s telemetry and stores it", async (event) => {
    const writeDataPoint = vi.fn();
    const installId = `install_${event}`;

    const response = await worker.fetch(
      telemetryRequest({
        install_id: installId,
        event,
        version: "1.2.3",
        os: "linux"
      }),
      telemetryEnv(writeDataPoint),
      createExecutionContext()
    );

    expect(response.status).toBe(204);
    await expect(response.text()).resolves.toBe("");
    await expect(countTelemetryRows(installId)).resolves.toBe(1);
    expect(writeDataPoint).toHaveBeenCalledOnce();
    expect(writeDataPoint).toHaveBeenCalledWith({
      blobs: [event, "1.2.3", "linux"],
      doubles: [1],
      indexes: [installId]
    });
  });

  it.each([
    ["invalid JSON", "{not json"],
    ["missing field", { install_id: "install_bad", event: "install", version: "1.0.0" }],
    ["wrong type", { install_id: "install_bad", event: "install", version: "1.0.0", os: 42 }],
    ["unknown event", { install_id: "install_bad", event: "bogus", version: "1.0.0", os: "linux" }],
    [
      "oversized install_id",
      { install_id: "x".repeat(97), event: "install", version: "1.0.0", os: "linux" }
    ],
    [
      "unknown key",
      { install_id: "install_bad", event: "install", version: "1.0.0", os: "linux", extra: true }
    ]
  ])("rejects %s payloads", async (_name, payload) => {
    const writeDataPoint = vi.fn();

    const response = await worker.fetch(
      telemetryRequest(payload),
      telemetryEnv(writeDataPoint),
      createExecutionContext()
    );

    expect(response.status).toBe(400);
    expect(writeDataPoint).not.toHaveBeenCalled();
  });

  it("returns 405 for non-POST methods", async () => {
    const response = await worker.fetch(
      telemetryRequest({}, "GET"),
      telemetryEnv(),
      createExecutionContext()
    );

    expect(response.status).toBe(405);
  });

  it("logs storage sink failures without failing a valid telemetry response", async () => {
    const writeDataPoint = vi.fn(() => {
      throw new Error("analytics down");
    });
    const failingDb = {
      prepare: () => {
        throw new Error("d1 down");
      }
    } as unknown as D1Database;
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const response = await worker.fetch(
      telemetryRequest({
        install_id: "install_storage_failure",
        event: "atlas_invoked",
        version: "1.2.3",
        os: "linux"
      }),
      telemetryEnv(writeDataPoint, { LICENSE_DB: failingDb }),
      createExecutionContext()
    );

    expect(response.status).toBe(204);
    expect(errorSpy).toHaveBeenCalled();
  });

  it("computes documented D1 KPI queries from seeded telemetry rows", async () => {
    await env.LICENSE_DB.prepare("DELETE FROM telemetry_events").run();
    const rows = [
      ["i1", "install", "1.0.0", "linux", "2026-06-01T00:00:00.000Z"],
      ["i1", "install", "1.0.0", "linux", "2026-06-01T01:00:00.000Z"],
      ["i2", "install", "1.0.0", "darwin", "2026-06-01T00:00:00.000Z"],
      ["i1", "atlas_invoked", "1.0.0", "linux", "2026-06-10T00:00:00.000Z"],
      ["i2", "reach_execute", "1.0.0", "darwin", "2026-06-10T00:00:00.000Z"],
      ["i2", "ship_check_ok", "1.0.0", "darwin", "2026-06-10T01:00:00.000Z"],
      ["i3", "atlas_invoked", "1.0.0", "linux", "2026-05-01T00:00:00.000Z"],
      ["i4", "reach_execute", "1.0.0", "linux", "2026-05-01T00:00:00.000Z"]
    ];
    for (const row of rows) {
      await env.LICENSE_DB.prepare(
        "INSERT INTO telemetry_events (install_id, event, version, os, timestamp) VALUES (?, ?, ?, ?, ?)"
      )
        .bind(...row)
        .run();
    }

    const a1 = await env.LICENSE_DB.prepare(
      "SELECT COUNT(DISTINCT install_id) AS value FROM telemetry_events WHERE event = 'install'"
    ).first<{ value: number }>();
    const a3 = await env.LICENSE_DB.prepare(
      "SELECT COUNT(DISTINCT install_id) AS value FROM telemetry_events WHERE event != 'install' AND timestamp > ?"
    )
      .bind("2026-06-04T00:00:00.000Z")
      .first<{ value: number }>();
    const ac1 = await env.LICENSE_DB.prepare(
      "SELECT COUNT(*) AS value FROM telemetry_events WHERE event = 'reach_execute'"
    ).first<{ value: number }>();
    const ac2 = await env.LICENSE_DB.prepare(
      "SELECT COUNT(*) AS value FROM telemetry_events WHERE event = 'ship_check_ok'"
    ).first<{ value: number }>();

    expect(a1?.value).toBe(2);
    expect(a3?.value).toBe(2);
    expect(ac1?.value).toBe(2);
    expect(ac2?.value).toBe(1);
  });
});
