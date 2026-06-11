import type { Env } from "./types";

const EVENTS = new Set(["install", "atlas_invoked", "reach_execute", "ship_check_ok"]);
const EXACT_KEYS = "event,install_id,os,version";
const MAX_INSTALL_ID_LENGTH = 96;
const MAX_LABEL_LENGTH = 80;

interface TelemetryPayload {
  install_id: string;
  event: "install" | "atlas_invoked" | "reach_execute" | "ship_check_ok";
  version: string;
  os: string;
}

function invalid(): Response {
  return new Response(null, { status: 400 });
}

function noContent(): Response {
  return new Response(null, { status: 204 });
}

function isBoundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength;
}

async function readTelemetryPayload(request: Request): Promise<TelemetryPayload | null> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return null;
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }

  const record = body as Record<string, unknown>;
  if (Object.keys(record).sort().join(",") !== EXACT_KEYS) {
    return null;
  }
  if (
    !isBoundedString(record.install_id, MAX_INSTALL_ID_LENGTH) ||
    !isBoundedString(record.version, MAX_LABEL_LENGTH) ||
    !isBoundedString(record.os, MAX_LABEL_LENGTH) ||
    typeof record.event !== "string" ||
    !EVENTS.has(record.event)
  ) {
    return null;
  }

  return {
    install_id: record.install_id,
    event: record.event as TelemetryPayload["event"],
    version: record.version,
    os: record.os
  };
}

function writeAnalytics(env: Env, payload: TelemetryPayload): void {
  try {
    env.TELEMETRY.writeDataPoint({
      blobs: [payload.event, payload.version, payload.os],
      doubles: [1],
      indexes: [payload.install_id]
    });
  } catch (error) {
    console.error("telemetry.analytics_write_failed", {
      installId: payload.install_id,
      message: error instanceof Error ? error.message : "Unknown Analytics Engine failure"
    });
  }
}

async function insertTelemetryEvent(
  env: Env,
  payload: TelemetryPayload,
  timestamp: string
): Promise<void> {
  try {
    await env.LICENSE_DB.prepare(
      `INSERT INTO telemetry_events (install_id, event, version, os, timestamp)
        VALUES (?, ?, ?, ?, ?)`
    )
      .bind(payload.install_id, payload.event, payload.version, payload.os, timestamp)
      .run();
  } catch (error) {
    console.error("telemetry.d1_insert_failed", {
      installId: payload.install_id,
      event: payload.event,
      message: error instanceof Error ? error.message : "Unknown D1 failure"
    });
  }
}

export async function handleTelemetry(request: Request, env: Env): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: { Allow: "POST" }
    });
  }

  const payload = await readTelemetryPayload(request);
  if (!payload) {
    return invalid();
  }

  writeAnalytics(env, payload);
  await insertTelemetryEvent(env, payload, new Date(Date.now()).toISOString());

  return noContent();
}
