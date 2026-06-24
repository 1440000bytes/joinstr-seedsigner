#!/bin/bash
# Record a demo video of the SeedSigner emulator signing a real joinstr coinjoin PSBT:
# Select Signer -> CoinJoin verification (your in/out/fee) -> Sign Transaction ->
# animated signed-PSBT QR. Output: demo.mp4
#
# Run with the sandbox disabled (Xvfb/ffmpeg need it):  bash record_demo.sh
set -e
ROOT=/home/test/joinstr-seedsigner
SRC=$ROOT/emulator/upstream/src
OUT=$ROOT/demo.mp4
CAP=/tmp/cap
export DISPLAY=:99

bitcoin-cli -datadir=/home/test/.joinstr-regtest -rpcwait getblockchaininfo >/dev/null
python3 $ROOT/prep_demo_psbt.py

pkill -f "Xvfb :99" 2>/dev/null || true; pkill -f emulator_demo.py 2>/dev/null || true; sleep 1
rm -rf $CAP; mkdir -p $CAP

Xvfb :99 -screen 0 800x560x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB=$!; sleep 2
xdpyinfo >/dev/null 2>&1 || { echo "Xvfb failed"; exit 1; }

cd "$SRC"
python3 $ROOT/emulator_demo.py >/tmp/emulator_demo.log 2>&1 &
EMU=$!
win() { xdotool search --name "SeedSigner Emulator" 2>/dev/null | head -1; }
press() { local w; w=$(win); [ -n "$w" ] && xdotool key --window "$w" "$1"; echo "[rec] press $1"; }
for i in $(seq 1 25); do W=$(win); [ -n "$W" ] && break; sleep 1; done
echo "[rec] window $W"
sleep 2

# capture the emulator window by id (~10 fps) in the background -- reliable framing
touch $CAP/.go
( n=0; while [ -f $CAP/.go ]; do n=$((n+1)); printf -v f "$CAP/f_%04d.png" $n
  import -window "$W" "$f" 2>/dev/null; sleep 0.05; done ) &
GRAB=$!
echo "[rec] grabbing window frames"

sleep 3      # Select Signer (pre-loaded seed highlighted)
press Return # pick seed -> overview -> auto-routes to CoinJoin screen
sleep 5      # linger on CoinJoin verification (in / out / fee)
press Return # "Sign my input" -> Sign Transaction confirmation
sleep 3      # Sign Transaction screen
press Return # "Approve transaction" -> signs this peer's input
sleep 7      # animated signed-PSBT QR plays

rm -f $CAP/.go; sleep 1; kill $GRAB 2>/dev/null || true
kill $EMU 2>/dev/null || true; kill $XVFB 2>/dev/null || true

NF=$(ls $CAP/f_*.png 2>/dev/null | wc -l)
echo "[rec] captured $NF frames; encoding..."
ffmpeg -y -framerate 10 -pattern_type glob -i "$CAP/f_*.png" \
  -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -pix_fmt yuv420p -vcodec libx264 -preset medium "$OUT" \
  >/tmp/ffmpeg.log 2>&1
echo "[rec] done -> $OUT"
ls -la "$OUT"
