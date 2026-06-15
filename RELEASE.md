# Release process

This package ships to npm as `prd-taskmaster`. Releases are gated so that an
**auth failure is caught in one second, before any expensive tag/build/publish work** —
not after the build is half-done and `npm publish` hangs on an interactive web-auth wall.

## Release gate order

Run the gates in this exact order. Each one fails closed (non-zero exit) and stops the release:

1. **`release:preflight` (npm auth)** — `npm run release:preflight`
   - Confirms a usable npm token exists **before** anything else.
   - Runs `scripts/check-npm-auth.mjs`. If no token is found it exits `1` immediately,
     *before any network call*, so it can never stall on a browser login.
2. **version-sync** — `npm run version:check`
   - `scripts/check-version-sync.js` — every version source-of-truth must agree
     (`package.json`, `.claude-plugin/plugin.json`, `prd_taskmaster/__init__.py`).
3. **tag** — `git tag vX.Y.Z && git push --tags`
4. **publish** — `npm publish`

### Automatic enforcement via `prepublishOnly`

`npm publish` runs the package's `prepublishOnly` script first. It now runs **auth, then
version-sync**:

```json
"prepublishOnly": "node scripts/check-npm-auth.mjs && node scripts/check-version-sync.js"
```

So even if you forget to run `release:preflight` by hand, `npm publish` will refuse to
proceed when npm auth is missing/expired — auth is checked **before** the publish does any
real work. This is the fix for the recurring "publish stalls on a browser web-auth timeout"
failure: you now fail fast at the gate instead of mid-publish.

## Auth: token path vs web-auth path

`scripts/check-npm-auth.mjs` looks for a token in two places (pure, offline detection):

### (a) Token path — preferred (non-interactive, no browser)

Either of:

- Set an environment variable:
  ```bash
  export NPM_TOKEN=<token>
  ```
  (The operator keeps an npm token in **Bitwarden** — retrieve it from there.)
- Or add a line to `~/.npmrc`:
  ```
  //registry.npmjs.org/:_authToken=<token>
  ```

Then re-run `npm run release:preflight` to confirm.

If a token is present, the preflight also runs `npm whoami` as a **soft** confirmation —
a network failure there is only a warning (the token may still be valid), and it never
blocks. The hard fail-closed behaviour only triggers when **no token at all** is found.

### (b) Web-auth path — only if no token is available

Run `npm login` in the operator's **real desktop browser** (already logged in, on their
own residential IP). Do **not** drive the login URL in an automated/headless browser — that
advertises automation and trips Cloudflare/Turnstile "Just a moment" challenges. Approve the
sign-in in one click, then re-run `npm run release:preflight`.

## One-shot release checklist

```bash
npm run release:preflight        # 1. auth — fails closed if no token
npm run version:check            # 2. versions agree
pytest tests/                    # (sanity — full suite stays green)
git tag vX.Y.Z && git push --tags  # 3. tag
npm publish                      # 4. publish (re-runs auth + version-sync via prepublishOnly)
```
