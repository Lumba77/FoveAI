#!/usr/bin/env bash
# XRL skeletonize helper — usage: xrl-skeletonize.sh <filepath> [level=4]
FILE=${1:-Backend/Cognition/soul_core.py}
LEVEL=${2:-4}
URL=${XRL_PROXY_URL:-http://127.0.0.1:8200}
curl -s -X POST "$URL/api/skeletonize" \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\",\"level\":$LEVEL}" | python -m json.tool
