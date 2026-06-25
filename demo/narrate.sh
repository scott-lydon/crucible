#!/usr/bin/env bash
# narrate.sh <out.mp3> <script.txt> [seed]
# Renders the user's ElevenLabs voice for a narration block. Reuses el_tts_render.
set -euo pipefail
OUT="$1"; SCRIPT="$2"; SEED="${3:-4242}"
set -a; . /Users/scottlydon/.config/conveyor/elevenlabs.env; set +a
source ~/.claude/skills/assignment-conveyor/lib/elevenlabs_tts.sh
TEXT="$(cat "$SCRIPT")"
rm -f "$OUT"
el_tts_render "$OUT" "$ELEVENLABS_VOICE_ID" "$TEXT" "" "$SEED"
DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT")
echo "narrated $OUT  dur=${DUR}s  bytes=$(stat -f%z "$OUT")"
