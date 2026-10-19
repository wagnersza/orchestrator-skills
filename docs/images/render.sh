#!/bin/sh
# Render each diagram in src/ to a PNG beside this script, at its own size, at 2x.
# Each page writes its size to <html data-size>, so a first headless pass reads it.
set -eu
cd "$(dirname "$0")/src"
CHROME=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
for page in *.html; do
  name=${page%.html}
  size=$("$CHROME" --headless=new --disable-gpu --window-size=2000,1400 --dump-dom "file://$PWD/$page" 2>/dev/null \
    | grep -o 'data-size="[0-9]*x[0-9]*"' | grep -o '[0-9]*x[0-9]*')
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size="${size%x*},${size#*x}" --screenshot="$PWD/../$name.png" "file://$PWD/$page" 2>/dev/null
  echo "$name.png $size"
done
