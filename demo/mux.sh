#!/usr/bin/env bash
# mux.sh <video.webm> <narration.mp3> <out.mp4>
# Lays the narration over the silent screen-capture. Final duration = max(video,
# audio): freezes the last video frame to cover any narration tail, pads audio
# with silence if the video runs longer. Encodes h264/aac mp4 for upload.
set -euo pipefail
VID="$1"; AUD="$2"; OUT="$3"
V=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VID")
A=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUD")
PAD=$(python3 -c "import sys; v,a=float('$V'),float('$A'); print(max(0.0, a-v+0.4))")
ffmpeg -y -loglevel error -i "$VID" -i "$AUD" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=${PAD}[v];[1:a]apad[a]" \
  -map "[v]" -map "[a]" -shortest \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k -movflags +faststart "$OUT"
OUTDUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT")
echo "muxed $OUT  vid=${V}s aud=${A}s out=${OUTDUR}s bytes=$(stat -f%z "$OUT")"
