#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== index.html 업데이트 ==="
cd "$REPO_ROOT/report/docs"

python3 update_index.py

if git diff --quiet && git diff --cached --quiet; then
  echo ""
  echo "변경 사항 없음 — 커밋 및 푸시를 건너뜁니다."
  exit 0
fi

TODAY=$(date +%Y-%m-%d)
git add .
git commit -m "update : ($TODAY) $@"

echo ""
echo "=== GitHub에 푸시 ==="
git push origin develop

echo ""
echo "완료!"
