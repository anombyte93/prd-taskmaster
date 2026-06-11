# Atlas License Key Specification v1

Atlas Pro license keys are offline-verifiable Ed25519 signatures over a small
canonical JSON payload. The private signing key must live only in Worker secrets
or a local signing environment outside the repository. The runtime client ships
only the embedded public key used to verify keys.

## Grammar

```
license-key = "ATLAS-" base64url(payload) "." base64url(sig)
payload     = canonical JSON object bytes
sig         = 64-byte Ed25519 signature over payload
```

The literal wire format is:

```
ATLAS-<base64url(payload)>.<base64url(sig)>
```

Both `payload` and `sig` use RFC 4648 URL-safe base64url with `=` padding
stripped. Decoders must reject padded segments and non-base64url characters.

## Payload Schema

Payloads are JSON objects with exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `lid` | string | License id issued by Atlas billing. |
| `sub` | string | Lowercase SHA-256 hex digest of the UTF-8 email argument. |
| `plan` | string | One of `pro-monthly` or `pro-annual`. |
| `iat` | integer | Issued-at Unix timestamp in seconds. |
| `exp` | integer | Expiry Unix timestamp in seconds, including grace. |
| `v` | integer | Format version. Must be `1`. |

`exp` is not the raw billing period end. It is the billing period end plus 14 days
of grace, so offline clients only compare `now <= exp`. No second grace window is
applied during verification.

## Canonical JSON

The signed payload bytes are canonical JSON:

- sort object keys lexicographically;
- use compact separators, with no insignificant whitespace;
- encode as UTF-8;
- include only `lid`, `sub`, `plan`, `iat`, `exp`, and `v`.

For Python this is equivalent to:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Every implementation signs and verifies those canonical JSON bytes, not a
pretty-printed or insertion-ordered representation.

## Signing And Verification

The signing algorithm is PureEdDSA Ed25519 as specified by RFC 8032. Private keys
are 32-byte Ed25519 seeds. Public keys are 32 bytes. Signatures are 64 bytes.

Signing:

1. Build the payload fields.
2. Serialize the payload as canonical JSON.
3. Sign those bytes with the private Ed25519 seed.
4. Emit `ATLAS-<base64url(payload)>.<base64url(sig)>`.

Verification:

1. Decode the prefix, payload segment, and signature segment.
2. Reject non-canonical payload JSON.
3. Validate every payload field and `v == 1`.
4. Verify the Ed25519 signature with the embedded public key.
5. Compare the verifier's current Unix time to `exp`.

The distributed verifier must embed or otherwise pin the Atlas public key. The
private signing seed is never shipped with the CLI, client, docs, tests, or repo.

## Cross-Implementation Contract

The committed fixture at `tests/license/test_vectors.json` is the compatibility
contract for Python CLI signers and Worker TypeScript signers. Any signer that
claims v1 compatibility must reproduce every reproducible fixture key
byte-for-byte from the fixture payloads.

The fixture classes are:

- `valid`: signature verifies and `now <= exp`;
- `expired`: signature verifies but `now > exp`;
- `tampered-payload`: payload bytes were changed after signing;
- `signature-mismatch`: signature was produced by a different key.

The deterministic fixture seed is test-only and non-secret. Production private
key material must be provisioned as Worker secrets or local signing env state.
