#!/usr/bin/env python3
"""
Basic joinstr <-> SeedSigner coinjoin, end to end on regtest.

Pipeline per the agreed architecture:
  - 2 peers, fixed denomination, ANYONECANPAY (0x81), no change  (as basic as floresta PR #1)
  - peer-1's input is signed through SeedSigner's OWN code path (Seed + PSBTParser + patched sign)
  - the signed PSBT is round-tripped through the UR-QR codec the emulator actually uses
  - merge + finalize + broadcast use py-joinstr's OWN functions (joinstrd.combine_psbts /
    finalize_and_broadcast) against bitcoind regtest
"""
import os, sys, json, base64, subprocess, hashlib

SS_SRC = "/home/test/joinstr-seedsigner/emulator/upstream/src"
JOINSTR = "/home/test/joinstr-seedsigner/joinstr/cli"
sys.path.insert(0, SS_SRC)
sys.path.insert(0, JOINSTR)

from embit import bip32, script, ec, bip39
from embit.psbt import PSBT, DerivationPath
from embit.transaction import Transaction, TransactionInput, TransactionOutput, SIGHASH
from embit.networks import NETWORKS

# SeedSigner's real device code
from seedsigner.models.seed import Seed
from seedsigner.models.psbt_parser import PSBTParser
from seedsigner.models.settings_definition import SettingsConstants
from seedsigner.models.encode_qr import UrPsbtQrEncoder
from seedsigner.helpers.ur2.ur_decoder import URDecoder
from urtypes.crypto import PSBT as UR_PSBT

# py-joinstr's real daemon code (module import loads config, does not start server)
import joinstrd

NET = NETWORKS["regtest"]
DATADIR = "/home/test/.joinstr-regtest"
ANYONECANPAY_ALL = SIGHASH.ALL | SIGHASH.ANYONECANPAY
DERIV = "m/84h/1h/0h/0/0"

def cli(*args, wallet=None):
    base = ["bitcoin-cli", f"-datadir={DATADIR}"]
    if wallet: base.append(f"-rpcwallet={wallet}")
    out = subprocess.run(base + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"bitcoin-cli {args} failed: {out.stderr.strip()}")
    return out.stdout.strip()

def mk_peer(tag):
    """A peer = a BIP39 mnemonic (what SeedSigner holds) + its derived key/address."""
    entropy = hashlib.sha256(tag.encode()).digest()[:16]
    mnemonic = bip39.mnemonic_from_bytes(entropy)
    root = bip32.HDKey.from_seed(bip39.mnemonic_to_seed(mnemonic), version=NET["xprv"])
    leaf = root.derive(DERIV)
    addr = script.p2wpkh(leaf.get_public_key()).address(NET)
    return {"tag": tag, "mnemonic": mnemonic, "root": root, "leaf": leaf, "addr": addr}

def fund(peer, sats):
    txid = cli("sendtoaddress", peer["addr"], f"{sats/1e8:.8f}", wallet="peerA")
    raw = json.loads(cli("getrawtransaction", txid, "true"))  # still in mempool, no txindex needed
    cli("generatetoaddress", "1", cli("getnewaddress", wallet="peerA"))
    vout = next(v["n"] for v in raw["vout"]
                if v["scriptPubKey"]["address"] == peer["addr"])
    return txid, vout, int(round(raw["vout"][vout]["value"] * 1e8)), bytes.fromhex(raw["hex"])

def build_unsigned(peer, prevout, all_outputs):
    """Each peer builds its own 1-input PSBT carrying ALL coinjoin outputs (joinstr model)."""
    txid, vout, value, rawhex = prevout
    prev_tx = Transaction.parse(rawhex)
    vin = [TransactionInput(bytes.fromhex(txid), vout)]
    vout_list = [TransactionOutput(amt, script.address_to_scriptpubkey(addr))
                 for addr, amt in all_outputs]
    psbt = PSBT(Transaction(vin=vin, vout=vout_list))
    psbt.inputs[0].witness_utxo = prev_tx.vout[vout]
    pub = peer["leaf"].get_public_key()
    psbt.inputs[0].bip32_derivations[pub] = DerivationPath(
        peer["root"].my_fingerprint, bip32.parse_path(DERIV))
    psbt.inputs[0].sighash_type = ANYONECANPAY_ALL   # joinstr requirement
    return psbt

def sign_via_seedsigner(unsigned_psbt, peer):
    """Exactly what the (patched) device does: Seed -> PSBTParser -> sign_with(sighash=None)."""
    seed = Seed(mnemonic=peer["mnemonic"].split())
    parser = PSBTParser(unsigned_psbt, seed, network=SettingsConstants.REGTEST)  # device verification model
    # ---- this is the patched PSBTFinalizeView.run() signing line ----
    before = PSBTParser.sig_count(unsigned_psbt)
    unsigned_psbt.sign_with(parser.root, sighash=None)
    after = PSBTParser.sig_count(unsigned_psbt)
    assert after > before, "SeedSigner produced no signature!"
    return unsigned_psbt, parser

def qr_roundtrip(signed_psbt):
    """Encode like the device screen, decode like the camera side -> prove transport works."""
    enc = UrPsbtQrEncoder(psbt=signed_psbt, qr_density=2)  # animated fountain QR
    dec = URDecoder()
    parts, guard = 0, 0
    while not dec.is_complete() and guard < 5000:
        dec.receive_part(enc.next_part()); parts += 1; guard += 1
    assert dec.is_complete(), "UR decode never completed"
    ur = dec.result_message()
    raw = UR_PSBT.from_cbor(ur.cbor).data
    return PSBT.parse(raw), parts

def main():
    print("== joinstr <-> SeedSigner coinjoin (regtest) ==\n")
    denom = 90_000
    fee_total = 2_000
    out_amt = denom - fee_total // 2   # per-output fee share (joinstr model)

    p1, p2 = mk_peer("seedsigner-peerA"), mk_peer("seedsigner-peerB")
    print(f"peer1 addr {p1['addr']}\npeer2 addr {p2['addr']}\n")
    u1 = fund(p1, denom + 5_000)
    u2 = fund(p2, denom + 5_000)
    print(f"funded peer1 utxo {u1[0][:16]}..:{u1[1]} ({u1[2]} sats)")
    print(f"funded peer2 utxo {u2[0][:16]}..:{u2[1]} ({u2[2]} sats)\n")

    # fresh coinjoin outputs (one fresh key each) -- equal value
    o1 = script.p2wpkh(p1["root"].derive("m/84h/1h/0h/1/7").get_public_key()).address(NET)
    o2 = script.p2wpkh(p2["root"].derive("m/84h/1h/0h/1/9").get_public_key()).address(NET)
    outs = sorted([(o1, out_amt), (o2, out_amt)])   # joinstr sorts outputs

    # ---- peer 1 signs through SeedSigner, then QR round-trip ----
    psbt1 = build_unsigned(p1, u1, outs)
    psbt1, parser1 = sign_via_seedsigner(psbt1, p1)
    print(f"[peer1] signed via SeedSigner code  (Seed+PSBTParser+patched sign_with)")
    psbt1_qr, nparts = qr_roundtrip(psbt1)
    print(f"[peer1] UR-QR round-trip OK over {nparts} animated frames "
          f"(sig byte 0x{list(psbt1_qr.inputs[0].partial_sigs.values())[0][-1]:02x})")
    p1_b64 = base64.b64encode(psbt1_qr.serialize()).decode()

    # ---- peer 2 is just another participant (signs with embit directly) ----
    psbt2 = build_unsigned(p2, u2, outs)
    psbt2.sign_with(p2["root"], sighash=None)
    p2_b64 = base64.b64encode(psbt2.serialize()).decode()
    print(f"[peer2] signed independently        (sig byte 0x"
          f"{list(psbt2.inputs[0].partial_sigs.values())[0][-1]:02x})\n")

    # ---- merge + finalize + broadcast via py-joinstr's OWN functions ----
    combined, err = joinstrd.combine_psbts([p1_b64, p2_b64])
    assert not err, f"combine_psbts failed: {err}"
    print(f"[joinstr] combine_psbts -> merged PSBT ({len(combined)} b64 chars)")
    txid, err = joinstrd.finalize_and_broadcast(combined)
    assert not err, f"finalize/broadcast failed: {err}"
    print(f"[joinstr] finalize_and_broadcast -> BROADCAST txid {txid}")

    tx = json.loads(cli("getrawtransaction", txid, "true"))  # from mempool, before mining
    blockhash = cli("generatetoaddress", "1", cli("getnewaddress", wallet="peerA"))
    tx = json.loads(cli("getrawtransaction", txid, "true", json.loads(blockhash)[0]))
    print(f"\n== CONFIRMED coinjoin: {len(tx['vin'])} inputs, {len(tx['vout'])} outputs, "
          f"confirmations={tx.get('confirmations',0)} ==")
    for v in tx["vout"]:
        print(f"   out {v['scriptPubKey']['address']}  {int(round(v['value']*1e8))} sats")

if __name__ == "__main__":
    main()
