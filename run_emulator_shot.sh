#!/bin/bash
# Boot the real SeedSigner emulator (Tkinter) under Xvfb and screenshot it.
set -u
SRC=/home/test/joinstr-seedsigner/emulator/upstream/src
export DISPLAY=:99

pkill -f "Xvfb :99" 2>/dev/null; pkill -f "main.py" 2>/dev/null; sleep 1
Xvfb :99 -screen 0 480x480x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB=$!
sleep 2
xdpyinfo >/dev/null 2>&1 && echo "[run] Xvfb up" || { echo "[run] Xvfb failed"; exit 1; }

cd "$SRC"
python3 main.py >/tmp/emulator.log 2>&1 &
EMU=$!
echo "[run] emulator pid $EMU, booting..."

# wait for the Tk window to appear
for i in $(seq 1 20); do
  sleep 1
  if xwininfo -root -tree 2>/dev/null | grep -qiE 'seedsigner|tk'; then
    echo "[run] window detected after ${i}s"; break
  fi
done
sleep 3   # let the home screen settle

import -window root /home/test/joinstr-seedsigner/shot_home.png 2>/tmp/import.log \
  && echo "[run] screenshot saved" || echo "[run] screenshot failed: $(cat /tmp/import.log)"

kill $EMU 2>/dev/null; kill $XVFB 2>/dev/null
echo "[run] done"
