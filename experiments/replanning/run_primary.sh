#!/bin/bash
# Primary confirmatory runs (docs/preregistration.md, section 4). One condition per
# invocation so each run fits the 2-hour background limit:
#   experiments/replanning/run_primary.sh NEVER
# Do NOT run before the preregistration has been approved.
set -euo pipefail
cd "$(dirname "$0")/../.."
declare -A SPEC=(
  [NEVER]="plan:replan=never,samples=62"
  [EV-1]="plan:replan=ev,check_every=1,samples=6"
  [EV-3]="plan:replan=ev,check_every=3,samples=16"
  [ALWAYS-1]="plan:replan=always,check_every=1,samples=6"
  [ALWAYS-3]="plan:replan=always,check_every=3,samples=16"
)
LABEL="$1"
OUT=results/replanning
mkdir -p "$OUT"
TMP="$OUT/.primary_${LABEL}.jsonl"
rm -f "$TMP"  # a crashed run is discarded and re-run in full (deterministic seeds)
echo "{\"label\": \"$LABEL\", \"spec\": \"${SPEC[$LABEL]}\", \"commit\": \"$(git rev-parse HEAD)\", \"started\": \"$(date -u +%FT%TZ)\"}" >> "$OUT/runs.jsonl"
python3 -m cascadia_bot.sweep --baseline greedy --games 800 --workers 4 --seed 1000000 \
  --games-out "$TMP" "${SPEC[$LABEL]}"
cat "$TMP" >> "$OUT/primary_games.jsonl"
rm -f "$TMP"
