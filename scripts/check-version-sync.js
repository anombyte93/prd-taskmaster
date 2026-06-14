#!/usr/bin/env node
/**
 * Pre-publish guard: every version source-of-truth must agree.
 *
 * Fixes the 5.2.1 miss — package.json + plugin.json were bumped but
 * prd_taskmaster/__init__.py (the source the manifest tests check) was not, and
 * the full suite wasn't re-run, so a mismatched build nearly shipped. Wired to
 * `prepublishOnly`, this makes `npm publish` REFUSE a drifted version.
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");

const initMatch = read("prd_taskmaster/__init__.py").match(
  /__version__\s*=\s*["']([^"']+)["']/
);

const versions = {
  "package.json": JSON.parse(read("package.json")).version,
  ".claude-plugin/plugin.json": JSON.parse(read(".claude-plugin/plugin.json")).version,
  "prd_taskmaster/__init__.py": initMatch ? initMatch[1] : null,
};

const unique = [...new Set(Object.values(versions))];

if (unique.length !== 1 || !unique[0]) {
  console.error("✖ version mismatch — all sources must agree before publish:");
  for (const [file, v] of Object.entries(versions)) {
    console.error(`    ${file}: ${v ?? "(unreadable)"}`);
  }
  console.error("\nBump every location (or run a single bump) and re-run the suite.");
  process.exit(1);
}

console.log(`✓ version sync OK: ${unique[0]}`);
