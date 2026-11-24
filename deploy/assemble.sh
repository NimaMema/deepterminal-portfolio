#!/usr/bin/env bash
# Assemble the Hugging Face Space folder from tracked files and the recorded snapshot.
#   deploy/assemble.sh <out-dir>
set -euo pipefail
OUT="${1:?usage: deploy/assemble.sh <out-dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
for f in deepterminal.dump cache.tar.gz showcase.json responses.json.gz; do
  test -s "deploy/snapshot/$f" || { echo "missing deploy/snapshot/$f (run scripts/build_demo_snapshot.py)"; exit 1; }
done
rm -rf "$OUT"; mkdir -p "$OUT"
git archive HEAD pyproject.toml README.md deepterminal backend frontend | tar -x -C "$OUT"
rm -rf "$OUT/backend/tests" "$OUT/frontend/e2e" "$OUT/frontend/tests"
cp deploy/huggingface/{Dockerfile,start.sh,warm.py,README.md,.gitattributes} "$OUT/"
cp -r deploy/snapshot "$OUT/snapshot"
du -sh "$OUT"
