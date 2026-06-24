"""Shared helpers for the joinstr <-> SeedSigner regtest demos."""
import sys, json, subprocess, hashlib, base64

SS_SRC = "/home/test/joinstr-seedsigner/emulator/upstream/src"
if SS_SRC not in sys.path:
    sys.path.insert(0, SS_SRC)

from embit import bip32, script, bip39
from embit.psbt import PSBT, DerivationPath
from embit.transaction import Transaction, TransactionInput, TransactionOutput, SIGHASH
from embit.networks import NETWORKS

from seedsigner.models.seed import Seed
from seedsigner.models.psbt_parser import PSBTParser
from seedsigner.models.settings_definition import SettingsConstants

NET = NETWORKS["regtest"]
DATADIR = "/home/test/.joinstr-regtest"
ANYONECANPAY_ALL = SIGHASH.ALL | SIGHASH.ANYONECANPAY
DERIV = "m/84h/1h/0h/0/0"


def cli(*args, wallet=None):
    base = ["bitcoin-cli", f"-datadir={DATADIR}"]
    if wallet:
        base.append(f"-rpcwallet={wallet}")
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


def fund(peer, sats, miner_wallet="peerA"):
    txid = cli("sendtoaddress", peer["addr"], f"{sats/1e8:.8f}", wallet=miner_wallet)
    raw = json.loads(cli("getrawtransaction", txid, "true"))  # mempool, no txindex needed
    cli("generatetoaddress", "1", cli("getnewaddress", wallet=miner_wallet))
    vout = next(v["n"] for v in raw["vout"]
                if v["scriptPubKey"]["address"] == peer["addr"])
    return txid, vout, int(round(raw["vout"][vout]["value"] * 1e8)), bytes.fromhex(raw["hex"])


def fresh_output_addr(peer, idx):
    return script.p2wpkh(peer["root"].derive(f"m/84h/1h/0h/1/{idx}").get_public_key()).address(NET)


def build_unsigned(peer, prevout, all_outputs, my_out_index=None):
    """A peer's 1-input PSBT carrying all coinjoin outputs; annotate own output if given."""
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
    psbt.inputs[0].sighash_type = ANYONECANPAY_ALL

    if my_out_index is not None:
        out_path = f"m/84h/1h/0h/1/{my_out_index}"
        out_pub = peer["root"].derive(out_path).get_public_key()
        my_spk = script.p2wpkh(out_pub).data
        for i, vo in enumerate(vout_list):
            if vo.script_pubkey.data == my_spk:
                psbt.outputs[i].bip32_derivations[out_pub] = DerivationPath(
                    peer["root"].my_fingerprint, bip32.parse_path(out_path))
                break
    return psbt


def sign_via_seedsigner(unsigned_psbt, peer):
    """Sign through SeedSigner's code path: Seed -> PSBTParser -> sign_with(sighash=None)."""
    seed = Seed(mnemonic=peer["mnemonic"].split())
    parser = PSBTParser(unsigned_psbt, seed, network=SettingsConstants.REGTEST)
    before = PSBTParser.sig_count(unsigned_psbt)
    unsigned_psbt.sign_with(parser.root, sighash=None)
    assert PSBTParser.sig_count(unsigned_psbt) > before, "SeedSigner produced no signature!"
    return base64.b64encode(unsigned_psbt.serialize()).decode()
