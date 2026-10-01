#!/usr/bin/env bash
# XRL resonance benchmark — usage: xrl-resonance-benchmark.sh <filepath>
set -euo pipefail
URL=${XRL_PROXY_URL:-http://127.0.0.1:8200}
FILE=${1:-Tools/foveated-memory/server.js}

echo "=== Target: $FILE ==="
RAW_LINES=$(wc -l < "$FILE")
RAW_CHARS=$(wc -c < "$FILE")
echo "Raw file: $RAW_LINES lines, $RAW_CHARS chars"

echo "=== Level 4 skeleton ==="
SKEL=$(curl -s -X POST "$URL/api/skeletonize" \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\",\"level\":4}")
SKEL_CHARS=$(echo "$SKEL" | wc -c)
echo "Skeleton chars: $SKEL_CHARS"

echo "=== Reduction ==="
python3 -c "raw=$RAW_CHARS; skel=$SKEL_CHARS; print(f'Saved {(1-skel/raw)*100:.1f}% of tokens ({raw} → {skel})')"

echo "=== Semantic summary ==="
curl -s -X POST "$URL/api/semantic-summary" \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\"}" | python -m json.tool
