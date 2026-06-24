#!/bin/bash
# One-shot: a real 2-peer joinstr coinjoin on regtest (signed via SeedSigner code,
# coordinated over nostr), then render the SeedSigner coinjoin verification screen.
#
# Requires: bitcoind/bitcoin-cli on PATH, Tor SOCKS on 127.0.0.1:9050, python deps.
set -e
ROOT=/home/test/joinstr-seedsigner
D=/home/test/.joinstr-regtest
BCLI="bitcoin-cli -datadir=$D"

echo "### 1/4  bitcoind regtest"
if ! $BCLI -rpcwait getblockchaininfo >/dev/null 2>&1; then
  bitcoind -datadir=$D -daemon >/dev/null; sleep 3
fi
$BCLI -rpcwait getblockchaininfo >/dev/null
$BCLI loadwallet peerA >/dev/null 2>&1 || $BCLI createwallet peerA >/dev/null 2>&1 || true
BAL=$($BCLI -rpcwallet=peerA getbalance)
if (( $(echo "$BAL < 1" | bc -l) )); then
  ADDR=$($BCLI -rpcwallet=peerA getnewaddress "" bech32)
  $BCLI generatetoaddress 101 "$ADDR" >/dev/null
fi
echo "    regtest ready, peerA balance $($BCLI -rpcwallet=peerA getbalance) BTC"

echo "### 2/4  clean stale joinstr state"
pkill -9 -f joinstrd.py 2>/dev/null || true
rm -f /home/test/.joinstr-A/pools.json /home/test/.joinstr-A/history.json \
      /home/test/.joinstr-B/pools.json /home/test/.joinstr-B/history.json
sleep 1

echo "### 3/4  run the live 2-peer coinjoin over nostr (takes ~1-3 min)"
cd $ROOT
python3 nostr_coinjoin.py

echo "### 4/4  render the SeedSigner coinjoin verification screen"
python3 screenshot_coinjoin.py 2>/dev/null | grep -E 'screenshot saved'
echo
echo "Open this to see the device screen the user approves:"
echo "    $ROOT/screenshots/PSBTCoinjoinOverviewView.png"
