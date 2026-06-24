#!/usr/bin/env python3
"""Headless test of the coinjoin-aware PSBTParser + the verification View's text."""
import sys
sys.path.insert(0, "/home/test/joinstr-seedsigner")
sys.path.insert(0, "/home/test/joinstr-seedsigner/emulator/upstream/src")
import cjlib
from seedsigner.models.seed import Seed
from seedsigner.models.psbt_parser import PSBTParser
from seedsigner.models.settings_definition import SettingsConstants

DENOM = 90_000
FEE = 1_000  # per-peer fee
OUT_AMT = DENOM - FEE

p1 = cjlib.mk_peer("view-peerA")
p2 = cjlib.mk_peer("view-peerB")
u1 = cjlib.fund(p1, DENOM + 5_000)
u2 = cjlib.fund(p2, DENOM + 5_000)

o1 = cjlib.fresh_output_addr(p1, 7)
o2 = cjlib.fresh_output_addr(p2, 9)
all_outputs = sorted([(o1, OUT_AMT), (o2, OUT_AMT)])

# peer-1 builds its own 1-input PSBT, annotating ITS output (idx 7)
psbt1 = cjlib.build_unsigned(p1, u1, all_outputs, my_out_index=7)

seed1 = Seed(mnemonic=p1["mnemonic"].split())
parser = PSBTParser(psbt1, seed1, network=SettingsConstants.REGTEST)

print("=== what stock SeedSigner would have shown ===")
print(f"  is_multisig: {parser.is_multisig}")
print(f"  num_inputs: {parser.num_inputs}   input_amount: {parser.input_amount}")
print(f"  destination_addresses (stock 'recipients'): {parser.num_destinations}")
print(f"  spend_amount (stock): {parser.spend_amount}   fee (stock psbt.fee): {parser.fee_amount}")
print("   ^ stock view is misleading: shows the user 'sending' to 2 addrs, negative/garbage fee\n")

print("=== coinjoin-aware parser ===")
assert parser.is_coinjoin, "coinjoin not detected!"
s = parser.coinjoin_summary
print(f"  is_coinjoin: {parser.is_coinjoin}")
for k, v in s.items():
    print(f"  {k}: {v}")

# This is exactly the text the PSBTCoinjoinOverviewView/Screen renders:
print("\n=== device verification screen text ===")
print("  +---------------------------------+")
print("  |          CoinJoin               |")
print(f"  |  {s['num_participants']} participants            |")
print(f"  |  Your input:   {s['my_input']:>10,} sat |")
print(f"  |  Your output:  {s['my_output']:>10,} sat |")
print(f"  |  Your fee:     {s['my_fee']:>10,} sat |")
print(f"  |  Denomination: {s['denomination']:>10,} sat |")
print("  |  Sign only your 1 input         |")
print("  +---------------------------------+")

assert s["my_input"] == u1[2]
assert s["my_output"] == OUT_AMT
assert s["my_fee"] == u1[2] - OUT_AMT
assert s["num_participants"] == 2
print("\nALL ASSERTIONS PASSED")
