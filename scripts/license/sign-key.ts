#!/usr/bin/env node

const crypto = require("node:crypto");

const KEY_PREFIX = "ATLAS-";
const PLANS = new Set(["pro-monthly", "pro-annual"]);
const PRIVATE_KEY_ENV = "ATLAS_LICENSE_PRIVATE_KEY_HEX";
const VECTOR_SEED_LABEL = "atlas-license-test-vector-seed-v1";
const PKCS8_ED25519_PREFIX = Buffer.from("302e020100300506032b657004220420", "hex");

function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    if (typeof value === "number" && !Number.isInteger(value)) {
      throw new Error("payload numbers must be integers");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
}

function canonicalPayloadBytes(payload) {
  validatePayload(payload);
  return Buffer.from(canonicalJson(payload), "utf8");
}

function b64url(data) {
  return Buffer.from(data)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function buildPayload({ lid, email, plan, iat, exp }) {
  return {
    lid,
    sub: crypto.createHash("sha256").update(email, "utf8").digest("hex"),
    plan,
    iat: Number(iat),
    exp: Number(exp),
    v: 1,
  };
}

function validatePayload(payload) {
  const keys = Object.keys(payload).sort().join(",");
  if (keys !== "exp,iat,lid,plan,sub,v") {
    throw new Error("payload fields must be exactly lid, sub, plan, iat, exp, v");
  }
  if (typeof payload.lid !== "string" || payload.lid.length === 0) {
    throw new Error("lid must be a non-empty string");
  }
  if (typeof payload.sub !== "string" || !/^[0-9a-f]{64}$/.test(payload.sub)) {
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

function privateKeyFromSeed(seed) {
  if (!Buffer.isBuffer(seed) || seed.length !== 32) {
    throw new Error("Ed25519 private seed must be 32 bytes");
  }
  return crypto.createPrivateKey({
    key: Buffer.concat([PKCS8_ED25519_PREFIX, seed]),
    format: "der",
    type: "pkcs8",
  });
}

function encodeLicenseKey(payload, signature) {
  if (!Buffer.isBuffer(signature) || signature.length !== 64) {
    throw new Error("Ed25519 signature must be 64 bytes");
  }
  return `${KEY_PREFIX}${b64url(canonicalPayloadBytes(payload))}.${b64url(signature)}`;
}

function signPayload(payload, privateSeed) {
  const signature = crypto.sign(null, canonicalPayloadBytes(payload), privateKeyFromSeed(privateSeed));
  return encodeLicenseKey(payload, signature);
}

function deterministicVectorSeed() {
  return crypto.createHash("sha256").update(VECTOR_SEED_LABEL, "utf8").digest();
}

function flagValue(args, flag) {
  const index = args.indexOf(flag);
  if (index === -1) {
    return undefined;
  }
  if (index + 1 >= args.length) {
    throw new Error(`${flag} requires a value`);
  }
  return args[index + 1];
}

function seedFromHex(hex) {
  if (!hex || !/^[0-9a-fA-F]{64}$/.test(hex)) {
    throw new Error("private key seed must be 64 hex characters");
  }
  return Buffer.from(hex, "hex");
}

function usage() {
  return [
    "Usage:",
    "  node sign-key.ts sign-payload --payload-json JSON [--private-key-hex HEX]",
    "  node sign-key.ts sign --lid ID --email EMAIL --plan PLAN --iat TS --exp TS [--private-key-hex HEX]",
    "",
    `sign uses --private-key-hex or ${PRIVATE_KEY_ENV}. sign-payload defaults to the fixture seed.`,
  ].join("\n");
}

function main(argv) {
  const [command, ...args] = argv;
  if (command === "--help" || command === "-h" || !command) {
    console.log(usage());
    return 0;
  }
  if (command === "sign-payload") {
    const payloadJson = flagValue(args, "--payload-json");
    if (!payloadJson) {
      throw new Error("--payload-json is required");
    }
    const seedHex = flagValue(args, "--private-key-hex");
    const seed = seedHex ? seedFromHex(seedHex) : deterministicVectorSeed();
    console.log(signPayload(JSON.parse(payloadJson), seed));
    return 0;
  }
  if (command === "sign") {
    const seed = seedFromHex(flagValue(args, "--private-key-hex") || process.env[PRIVATE_KEY_ENV]);
    const payload = buildPayload({
      lid: flagValue(args, "--lid"),
      email: flagValue(args, "--email"),
      plan: flagValue(args, "--plan"),
      iat: flagValue(args, "--iat"),
      exp: flagValue(args, "--exp"),
    });
    console.log(signPayload(payload, seed));
    return 0;
  }
  throw new Error(`unknown command: ${command}\n${usage()}`);
}

module.exports = {
  buildPayload,
  canonicalPayloadBytes,
  encodeLicenseKey,
  signPayload,
};

if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    console.error(`error: ${error.message}`);
    process.exitCode = 2;
  }
}
