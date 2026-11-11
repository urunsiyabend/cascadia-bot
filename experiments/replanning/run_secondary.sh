#!/bin/bash
# Secondary budget-sensitivity runs (docs/preregistration.md, section 6):
#   experiments/replanning/run_secondary.sh EV-1x3
# 400 games = the first 200 primary seeds, both seat orders.
# Do NOT run before the preregistration has been approved.
set -euo pipefail
cd "$(dirname "$0")/../.."
declare -A SPEC=(
  [EV-1x3]="plan:replan=ev,check_every=1,samples=18"
  [ALWAYS-1x3]="plan:replan=always,check_every=1,samples=18"
)
LABEL="$1"
OUT=results/replanning
mkdir -p "$OUT"
TMP="$OUT/.secondary_${LABEL}.jsonl"
rm -f "$TMP"
echo "{\"label\": \"$LABEL\", \"spec\": \"${SPEC[$LABEL]}\", \"commit\": \"$(git rev-parse HEAD)\", \"started\": \"$(date -u +%FT%TZ)\"}" >> "$OUT/runs.jsonl"
python3 -m cascadia_bot.sweep --baseline greedy --games 400 --workers 4 --seed 1000000 \
  --games-out "$TMP" "${SPEC[$LABEL]}"
cat "$TMP" >> "$OUT/secondary_games.jsonl"
rm -f "$TMP"
