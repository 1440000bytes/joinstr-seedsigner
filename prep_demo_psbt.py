#!/usr/bin/env python3
"""Fund a peer on regtest and build a real joinstr coinjoin PSBT (1 input, 2 equal
outputs, sighash 0x81, own output annotated). Write PSBT b64 + seed mnemonic to /tmp
for emulator_demo.py to ingest."""
import sys, base64
sys.path.insert(0, "/home/test/joinstr-seedsigner")
import cjlib

DENOM, FEE = 90_000, 1_000
OUT_AMT = DENOM - FEE
p1, p2 = cjlib.mk_peer("video-peerA"), cjlib.mk_peer("video-peerB")
u1 = cjlib.fund(p1, DENOM + 5_000)
o1 = cjlib.fresh_output_addr(p1, 7)
o2 = cjlib.fresh_output_addr(p2, 9)
all_outputs = sorted([(o1, OUT_AMT), (o2, OUT_AMT)])
psbt = cjlib.build_unsigned(p1, u1, all_outputs, my_out_index=7)

open("/tmp/joinstr_demo_psbt.txt", "w").write(base64.b64encode(psbt.serialize()).decode())
open("/tmp/joinstr_demo_seed.txt", "w").write(p1["mnemonic"])
print(f"PSBT ready: input {u1[2]} sats, 2x {OUT_AMT} outputs, mnemonic '{p1['mnemonic'].split()[0]} ...'")
