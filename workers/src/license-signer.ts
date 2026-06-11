const KEY_PREFIX = "ATLAS-";
const PKCS8_ED25519_PREFIX = "302e020100300506032b657004220420";
const PLANS = new Set(["pro-monthly", "pro-annual"]);

export interface LicensePayload {
  lid: string;
  sub: string;
  plan: "pro-monthly" | "pro-annual";
  iat: number;
  exp: number;
  v: 1;
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
    .join(",")}}`;
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function hexToBytes(hex: string): Uint8Array {
  if (!/^[0-9a-fA-F]+$/.test(hex) || hex.length % 2 !== 0) {
    throw new Error("hex input must contain an even number of hex characters");
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function validatePayload(payload: LicensePayload): void {
  const keys = Object.keys(payload).sort().join(",");
  if (keys !== "exp,iat,lid,plan,sub,v") {
    throw new Error("payload fields must be exactly lid, sub, plan, iat, exp, v");
  }
  if (!payload.lid) {
    throw new Error("lid must be a non-empty string");
  }
  if (!/^[0-9a-f]{64}$/.test(payload.sub)) {
    throw new Error("sub must be a lowercase SHA-256 hex digest");
  }
  if (!PLANS.has(payload.plan)) {
    throw new Error("plan must be pro-monthly or pro-annual");
  }
  if (!Number.isInteger(payload.iat) || !Number.isInteger(payload.exp)) {
    throw new Error("iat and exp must be integer Unix timestamps");
  }
  if (payload.exp < payload.iat) {
    throw new Error("exp must be greater than or equal to iat");
  }
  if (payload.v !== 1) {
    throw new Error("v must be 1");
  }
}

export function canonicalPayloadBytes(payload: LicensePayload): Uint8Array {
  validatePayload(payload);
  return new TextEncoder().encode(canonicalJson(payload));
}

export async function signLicensePayload(
  payload: LicensePayload,
  privateSeedHex: string
): Promise<string> {
  const seed = hexToBytes(privateSeedHex);
  if (seed.length !== 32) {
    throw new Error("Ed25519 private seed must be 32 bytes");
  }

  const privateKey = await crypto.subtle.importKey(
    "pkcs8",
    hexToBytes(`${PKCS8_ED25519_PREFIX}${privateSeedHex}`),
    { name: "Ed25519" },
    false,
    ["sign"]
  );
  const payloadBytes = canonicalPayloadBytes(payload);
  const signature = new Uint8Array(await crypto.subtle.sign("Ed25519", privateKey, payloadBytes));

  return `${KEY_PREFIX}${bytesToBase64Url(payloadBytes)}.${bytesToBase64Url(signature)}`;
}
