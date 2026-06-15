// Run with: node --test scripts/check-npm-auth.test.mjs
//
// Covers the pure resolveNpmAuth detection (offline, no network) and the CLI
// fail-closed guarantee: the no-token path must exit non-zero WITHOUT touching
// the network (no `npm whoami`), so it can never hang on a publish web-auth wall.

import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolveNpmAuth } from "./check-npm-auth.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(__dirname, "check-npm-auth.mjs");

test("resolveNpmAuth: NPM_TOKEN present → ok, method NPM_TOKEN", () => {
  const r = resolveNpmAuth({ env: { NPM_TOKEN: "npm_abc123" }, npmrc: "" });
  assert.equal(r.ok, true);
  assert.equal(r.method, "NPM_TOKEN");
});

test("resolveNpmAuth: NODE_AUTH_TOKEN present → ok, method NPM_TOKEN", () => {
  const r = resolveNpmAuth({ env: { NODE_AUTH_TOKEN: "npm_ci_token" }, npmrc: "" });
  assert.equal(r.ok, true);
  assert.equal(r.method, "NPM_TOKEN");
});

test("resolveNpmAuth: npmrc with _authToken → ok, method npmrc-token", () => {
  const npmrc = "//registry.npmjs.org/:_authToken=npm_fromfile\n";
  const r = resolveNpmAuth({ env: {}, npmrc });
  assert.equal(r.ok, true);
  assert.equal(r.method, "npmrc-token");
});

test("resolveNpmAuth: neither → not ok, method null", () => {
  const r = resolveNpmAuth({ env: {}, npmrc: "" });
  assert.equal(r.ok, false);
  assert.equal(r.method, null);
});

test("resolveNpmAuth: empty NPM_TOKEN string is not a token", () => {
  const r = resolveNpmAuth({ env: { NPM_TOKEN: "   " }, npmrc: "" });
  assert.equal(r.ok, false);
  assert.equal(r.method, null);
});

test("resolveNpmAuth: commented-out _authToken line does not count", () => {
  const npmrc = "# //registry.npmjs.org/:_authToken=npm_disabled\n";
  const r = resolveNpmAuth({ env: {}, npmrc });
  assert.equal(r.ok, false);
});

test("resolveNpmAuth: _authToken line with empty value does not count", () => {
  const npmrc = "//registry.npmjs.org/:_authToken=\n";
  const r = resolveNpmAuth({ env: {}, npmrc });
  assert.equal(r.ok, false);
});

test("resolveNpmAuth: env token wins even when npmrc has none", () => {
  const r = resolveNpmAuth({ env: { NPM_TOKEN: "npm_env" }, npmrc: "registry=https://x\n" });
  assert.equal(r.ok, true);
  assert.equal(r.method, "NPM_TOKEN");
});

test("CLI: no-token path exits non-zero with a FAIL message and does not hang", () => {
  // Temp HOME with an EMPTY .npmrc, env scrubbed of any npm token.
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), "npmauth-test-"));
  fs.writeFileSync(path.join(tmpHome, ".npmrc"), "", "utf8");

  const env = { ...process.env };
  delete env.NPM_TOKEN;
  delete env.NODE_AUTH_TOKEN;
  env.HOME = tmpHome;
  env.USERPROFILE = tmpHome; // Windows-safe, harmless on POSIX

  const res = spawnSync(process.execPath, [SCRIPT], {
    env,
    encoding: "utf8",
    timeout: 20000, // if it ever hangs on network, the test fails loudly instead
  });

  fs.rmSync(tmpHome, { recursive: true, force: true });

  assert.equal(res.error, undefined, `spawn must not error/timeout: ${res.error}`);
  assert.equal(res.status, 1, "no-token CLI must exit 1 (fail closed)");
  const out = `${res.stdout}\n${res.stderr}`;
  assert.match(out, /FAIL/, "must print a FAIL message");
  // Prove it exited BEFORE any whoami network probe.
  assert.doesNotMatch(out, /authenticated to npm registry/, "must not have reached whoami");
});
