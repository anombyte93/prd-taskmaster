#!/usr/bin/env node
/**
 * Release-auth preflight — FAILS CLOSED before any expensive tag/build/publish work.
 *
 * The recurring failure this guards: `npm publish` stalls on a browser web-auth
 * timeout because nobody checked that npm auth was actually valid FIRST. Wired ahead
 * of version-sync in `prepublishOnly`, this refuses to start a publish when no usable
 * npm token is present — so the operator finds out in one second, not after the tag/
 * build is half-done and the publish hangs on an interactive login.
 *
 * Design: the detection logic (`resolveNpmAuth`) is a PURE function with no network
 * and no filesystem access, so it is unit-testable offline. The CLI wrapper reads the
 * real environment + `~/.npmrc`, and only AFTER confirming a token exists does it
 * optionally probe the network via `npm whoami` (soft — a network failure is a warning,
 * never a crash, and never blocks the no-token fail-closed exit).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const REGISTRY_AUTH_LINE = "//registry.npmjs.org/:_authToken=";

/**
 * Pure auth-detection. No network, no filesystem — everything is passed in.
 *
 * @param {{ env?: Record<string,string|undefined>, npmrc?: string }} input
 *   env   — a process.env-like object; NPM_TOKEN (or NODE_AUTH_TOKEN) means a token.
 *   npmrc — the raw text of an .npmrc file (may be empty/undefined).
 * @returns {{ ok: boolean, method: ("NPM_TOKEN"|"npmrc-token"|null), why: string }}
 */
export function resolveNpmAuth({ env = {}, npmrc = "" } = {}) {
  // 1) Environment token wins — this is how CI and the Bitwarden-token path inject auth.
  const envToken = env.NPM_TOKEN || env.NODE_AUTH_TOKEN;
  if (typeof envToken === "string" && envToken.trim() !== "") {
    return {
      ok: true,
      method: "NPM_TOKEN",
      why: "NPM_TOKEN (or NODE_AUTH_TOKEN) is set in the environment.",
    };
  }

  // 2) An //registry.npmjs.org/:_authToken=... line in the npmrc string.
  if (typeof npmrc === "string" && npmrc.length > 0) {
    const hasAuthToken = npmrc
      .split(/\r?\n/)
      .map((line) => line.trim())
      .some(
        (line) =>
          !line.startsWith("#") &&
          !line.startsWith(";") &&
          // anchor on the line start (already trimmed) so a crafted host segment
          // like //evil.com//registry.npmjs.org/:_authToken= can't false-pass.
          line.startsWith(REGISTRY_AUTH_LINE) &&
          // require a non-empty value after the '='
          line.slice(REGISTRY_AUTH_LINE.length).trim() !== ""
      );
    if (hasAuthToken) {
      return {
        ok: true,
        method: "npmrc-token",
        why: `Found '${REGISTRY_AUTH_LINE}...' in the provided .npmrc.`,
      };
    }
  }

  // 3) Nothing usable.
  return {
    ok: false,
    method: null,
    why: "No NPM_TOKEN in the environment and no //registry.npmjs.org/:_authToken line in ~/.npmrc.",
  };
}

/** Read a file as text, returning "" if it does not exist / is unreadable. */
function readNpmrc(npmrcPath) {
  try {
    return fs.readFileSync(npmrcPath, "utf8");
  } catch {
    return "";
  }
}

/** The FAIL banner — documents both remediation paths. Returns the string for testability. */
function failMessage() {
  return [
    "✖ FAIL: npm release-auth preflight — no usable npm auth found.",
    "  Refusing to start publish work (tag/build/version-sync) with no valid token.",
    "",
    "  Two ways to fix this BEFORE retrying the release:",
    "",
    "  (a) Token path (preferred — non-interactive, no browser):",
    "      • export NPM_TOKEN=<token>    (the operator keeps an npm token in Bitwarden),",
    "        OR",
    "      • add this line to ~/.npmrc:",
    `          ${REGISTRY_AUTH_LINE}<token>`,
    "      then re-run:  npm run release:preflight",
    "",
    "  (b) Web-auth path (only if no token is available):",
    "      • run `npm login` in the operator's REAL browser (their own desktop browser,",
    "        already logged in on their residential IP — not an automated/headless one,",
    "        which trips Cloudflare/Turnstile). Complete the one-click approval, then",
    "        re-run:  npm run release:preflight",
  ].join("\n");
}

function main() {
  const env = process.env;
  const npmrcPath = path.join(os.homedir(), ".npmrc");
  const npmrc = readNpmrc(npmrcPath);

  const result = resolveNpmAuth({ env, npmrc });

  if (!result.ok) {
    // FAIL CLOSED — exit BEFORE any network call (no `npm whoami`), so this can never hang.
    console.error(failMessage());
    console.error(`\n  detail: ${result.why}`);
    process.exit(1);
  }

  // A token exists. Report HOW we found it.
  const where =
    result.method === "NPM_TOKEN"
      ? "environment (NPM_TOKEN / NODE_AUTH_TOKEN)"
      : `npmrc (${npmrcPath})`;
  console.log(`✓ npm token present via ${result.method} — ${where}.`);

  // OPTIONAL network confirmation. Soft: a failure here is a warning, never a crash,
  // because the token may be valid even when whoami can't reach the registry (offline,
  // proxy, registry blip). The fail-closed guarantee above does not depend on this.
  try {
    const who = execFileSync("npm", ["whoami"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 15000,
    }).trim();
    console.log(`✓ PASS: authenticated to npm registry as '${who}'.`);
  } catch (err) {
    const reason = (err && (err.stderr || err.message) ? String(err.stderr || err.message) : "")
      .trim()
      .split(/\r?\n/)[0];
    console.warn(
      "⚠ WARN: token present but `npm whoami` could not confirm it" +
        (reason ? ` (${reason})` : "") +
        ".\n  Treating as a soft warning — proceeding. If the publish 401s, the token may be expired/invalid."
    );
    console.log("✓ PASS (soft): token present; whoami unverified.");
  }
}

// Only run main() when executed directly, so tests can import resolveNpmAuth without
// triggering the CLI side effects (reading ~/.npmrc, process.exit, network).
// Use pathToFileURL so paths with spaces or symlinked invocations still match —
// a naive `file://${argv[1]}` compare silently skips main() (and thus the whole
// auth check) when the install path contains a space or is a symlink.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
