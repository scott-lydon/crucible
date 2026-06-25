#!/usr/bin/env bash
# stitch.sh <clips_dir> <out.mp4> <subtitle>
set -euo pipefail
DIR="$1"; OUT="$2"; SUB="${3:-local real-LLM run}"
TMP="$(dirname "$OUT")/_stitch_tmp"; mkdir -p "$TMP"
PY=python3
$PY demo/make_card.py "$TMP/title.png" "Crucible" "Adversarial robustness for AI targets" "Acceptance demo - US-1 to US-15 - $SUB" >/dev/null
$PY demo/make_card.py "$TMP/outro.png" "Crucible" "15 user stories - every value from real APIs" "github.com/scott-lydon/crucible - PR #3" >/dev/null
card_vid() { # png dur out
  ffmpeg -y -loglevel error -loop 1 -i "$1" -f lavfi -i "anullsrc=r=44100:cl=mono" \
    -t "$2" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
    -c:a aac -ar 44100 -ac 1 -movflags +faststart "$3"
}
card_vid "$TMP/title.png" 4.5 "$TMP/title.mp4"
card_vid "$TMP/outro.png" 3.5 "$TMP/outro.mp4"
LIST="$TMP/list.txt"; : > "$LIST"
echo "file '$(cd "$TMP" && pwd)/title.mp4'" >> "$LIST"
for i in $(seq 1 15); do echo "file '$(cd "$DIR" && pwd)/us$i.mp4'" >> "$LIST"; done
echo "file '$(cd "$TMP" && pwd)/outro.mp4'" >> "$LIST"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$LIST" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -ar 44100 -ac 1 -movflags +faststart "$OUT"
DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT")
echo "master $OUT  dur=${DUR}s  bytes=$(stat -f%z "$OUT")"
