#!/bin/bash
set -e
ROOT=/home/test/joinstr-seedsigner
export DISPLAY=:99
bitcoin-cli -datadir=/home/test/.joinstr-regtest -rpcwait getblockchaininfo >/dev/null
python3 $ROOT/prep_demo_psbt.py
pkill -f "Xvfb :99" 2>/dev/null || true; pkill -f emulator_demo.py 2>/dev/null || true; sleep 1
Xvfb :99 -screen 0 800x560x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 2
cd $ROOT/emulator/upstream/src
python3 $ROOT/emulator_demo.py >/tmp/emulator_demo.log 2>&1 &
EMU=$!
win(){ xdotool search --name "SeedSigner Emulator" 2>/dev/null | head -1; }
for i in $(seq 1 25); do W=$(win); [ -n "$W" ] && break; sleep 1; done
echo "win=$W geometry: $(xdotool getwindowgeometry "$W" 2>/dev/null | tr '\n' ' ')"
sleep 4;  import -window "$W" /tmp/d1_seed.png 2>/dev/null; echo "d1 (select seed)"
xdotool key --window "$W" Return; sleep 4
import -window "$W" /tmp/d2_coinjoin.png 2>/dev/null; echo "d2 (coinjoin)"
xdotool key --window "$W" Return; sleep 4
import -window "$W" /tmp/d3_finalize.png 2>/dev/null; echo "d3 (finalize)"
xdotool key --window "$W" Return; sleep 5
import -window "$W" /tmp/d4_signed.png 2>/dev/null; echo "d4 (signed)"
kill $EMU 2>/dev/null || true; pkill -f "Xvfb :99" 2>/dev/null || true
echo "=== log tail ==="; grep -viE 'font load|Supersampl|INFO:|Locale' /tmp/emulator_demo.log | grep -iE 'error|traceback|complete|sign|coinjoin|invalid|psbt' | tail -8
