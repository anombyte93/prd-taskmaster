#!/usr/bin/env bash
# Regenerate the Atlas internal architecture diagram suite.
#   - auto-derived graphs (pyreverse / code2flow / pydeps + AST fn-map) -> generated/
#   - hand-authored sources (src/*.d2, src/*.mmd) rendered -> rendered/
#
# Requires on PATH: python3, d2, mmdc (@mermaid-js/mermaid-cli), dot (graphviz),
#                   rsvg-convert (librsvg), chromium (for mmdc).
# Analyzers (pylint/pydeps/code2flow) are installed into a throwaway venv at /tmp.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PKG="$REPO/prd_taskmaster"
SRC="$HERE/src"; GEN="$HERE/generated"; REND="$HERE/rendered"
mkdir -p "$GEN" "$REND"

VENV=/tmp/atlas-diagrams-venv
python3 -m venv "$VENV" 2>/dev/null || true
"$VENV/bin/pip" install -q --disable-pip-version-check pylint pydeps code2flow

echo "==> auto-derive (pyreverse / code2flow / fn-map / pydeps)"
"$VENV/bin/pyreverse" -o mmd -p AtlasEngine -d "$GEN" "$PKG/"        # 30 import + class (.mmd)
"$VENV/bin/pyreverse" -o svg -p AtlasEngine -d "$GEN" "$PKG/" 2>/dev/null || true
CORE=(pipeline shipcheck validation tasks task_state fleet parallel backend provider_resolver economy preflight mode_recommend lib)
"$VENV/bin/code2flow" --language py -o "$GEN/callflow-core.dot" \
  "${CORE[@]/#/$PKG/}" >/dev/null 2>&1 || \
  "$VENV/bin/code2flow" --language py -o "$GEN/callflow-core.dot" $(printf "%s.py " "${CORE[@]/#/$PKG/}")
# (the line above tolerates code2flow needing explicit .py paths)
dot -Tsvg "$GEN/callflow-core.dot" -o "$GEN/callflow-core.svg"
python3 "$HERE/gen-fnmap.py" "$PKG" > "$GEN/20-module-function-map.md"
"$VENV/bin/pydeps" "$PKG" --no-output --show-cycles > "$GEN/30-import-cycles.txt" 2>&1 || true

echo "==> puppeteer config for mmdc (system chromium)"
CHROME="$(command -v chromium || command -v chromium-browser || true)"
PUP=/tmp/puppeteer-mmd.json
printf '{ "executablePath": "%s", "args": ["--no-sandbox","--disable-gpu"] }\n' "$CHROME" > "$PUP"

echo "==> render mermaid (src/*.mmd)"
for m in "$SRC"/*.mmd; do
  b="$(basename "$m" .mmd)"
  mmdc -p "$PUP" -i "$m" -o "$REND/$b.svg"
  rsvg-convert -z 1.4 -o "$REND/$b.png" "$REND/$b.svg"
  echo "   $b"
done

echo "==> render d2 (src/*.d2)"
for d in "$SRC"/*.d2; do
  b="$(basename "$d" .d2)"
  d2 --layout elk "$d" "$REND/$b.svg"
  rsvg-convert -z 1.5 -o "$REND/$b.png" "$REND/$b.svg"
  echo "   $b"
done

echo "==> done. sources in src/, auto-derived in generated/, images in rendered/."
