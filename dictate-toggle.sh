#!/bin/sh
# Start dictate in the background; run again to stop it.
DIR="$(cd "$(dirname "$0")" && pwd)"
if pkill -f "$DIR/dictate.py"; then
  notify-send -i audio-input-microphone "Dictate" "Stopped"
else
  notify-send -i audio-input-microphone "Dictate" "Starting... hold f9 to talk"
  exec "$DIR/.venv/bin/python" "$DIR/dictate.py" >> /tmp/dictate.log 2>&1
fi
