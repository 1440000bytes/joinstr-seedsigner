#!/usr/bin/env python3
"""
LIVE 2-peer joinstr coinjoin over real nostr (nos.lol via Tor), driven through
two joinstrd REST instances. Each peer signs its input through SeedSigner's code.

Peer A = creator (daemon on :8001, JOINSTR_DIR ~/.joinstr-A)
Peer B = joiner  (daemon on :8002, JOINSTR_DIR ~/.joinstr-B)
"""
import sys, os, time, json, subprocess, signal
import requests
sys.path.insert(0, "/home/test/joinstr-seedsigner")
import cjlib

JOINSTRD = "/home/test/joinstr-seedsigner/joinstr/cli/joinstrd.py"
A = "http://127.0.0.1:8001"
B = "http://127.0.0.1:8002"
DENOM_BTC = 0.0009          # 90_000 sats
PEERS = 2
POOL_TIMEOUT = 600          # seconds the pool stays open


def log(m): print(f"[orch] {m}", flush=True)


def start_daemon(letter, port):
    env = dict(os.environ, JOINSTR_DIR=f"/home/test/.joinstr-{letter}",
               JOINSTRD_HOST="127.0.0.1", JOINSTRD_PORT=str(port))
    f = open(f"/tmp/joinstrd-{letter}.log", "w")
    p = subprocess.Popen([sys.executable, JOINSTRD], env=env, stdout=f, stderr=subprocess.STDOUT)
    return p


def wait_up(base, timeout=60):
    for _ in range(timeout):
        try:
            if requests.get(f"{base}/status", timeout=3).ok:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_status(base, pk, want, timeout):
    """Poll /pool/status until it reaches `want` (or any later stage)."""
    order = ["output-registration", "input-registration", "success"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = requests.get(f"{base}/pool/status", params={"public_key": pk}, timeout=5).json()
            st = s.get("status", "")
            if st in order and order.index(st) >= order.index(want):
                return st
            if st == "timed-out":
                raise RuntimeError("pool timed out")
        except requests.RequestException:
            pass
        time.sleep(4)
    raise TimeoutError(f"status never reached {want} (last={st!r})")


def register_output_retry(base, pk, addr, timeout):
    """Retry register-output until it succeeds (joiner waits for pool credentials)."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        r = requests.post(f"{base}/pool/register-output",
                          json={"public_key": pk, "address": addr}, timeout=30)
        if r.ok:
            return r.json()
        last = r.text
        time.sleep(5)
    raise TimeoutError(f"register-output never succeeded ({last})")


def wait_outputs(base, pk, n, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        outs = requests.get(f"{base}/pool/outputs", params={"public_key": pk}, timeout=5).json()["outputs"]
        if len(outs) >= n:
            return outs
        time.sleep(4)
    raise TimeoutError(f"only {len(outs)}/{n} outputs registered")


def main():
    procs = []
    try:
        # ---- fund the two peers from regtest ----
        pA, pB = cjlib.mk_peer("nostr-peerA"), cjlib.mk_peer("nostr-peerB")
        uA = cjlib.fund(pA, 95_000)
        uB = cjlib.fund(pB, 95_000)
        log(f"funded A {uA[0][:12]}..:{uA[1]} and B {uB[0][:12]}..:{uB[1]}")

        # ---- boot both daemons ----
        procs = [start_daemon("A", 8001), start_daemon("B", 8002)]
        assert wait_up(A) and wait_up(B), "daemons did not come up"
        log("both daemons up (:8001 creator, :8002 joiner)")

        # ---- A creates the pool, publishes kind-2022 announcement to nostr ----
        pool = requests.post(f"{A}/pool/create",
                             json={"denomination": DENOM_BTC, "peers": PEERS, "timeout": POOL_TIMEOUT},
                             timeout=30).json()
        pk = pool["public_key"]
        log(f"pool created, pubkey {pk[:16]}.. announced on nos.lol")

        # ---- B discovers + joins the pool over nostr ----
        # (relay propagation can lag; retry the join until the event is visible)
        for attempt in range(20):
            r = requests.post(f"{B}/pool/join", json={"public_key": pk}, timeout=30)
            if r.ok:
                log(f"B joined pool (attempt {attempt+1})"); break
            time.sleep(5)
        else:
            raise RuntimeError(f"B could not find pool on relay: {r.text}")

        # ---- both register a fresh output address ----
        # A (creator) has the pool key immediately; B (joiner) only after the
        # creator DMs it the credentials, so register-output is retried until 200.
        outA = cjlib.fresh_output_addr(pA, 7)
        outB = cjlib.fresh_output_addr(pB, 9)
        rA = register_output_retry(A, pk, outA, 120)
        rB = register_output_retry(B, pk, outB, 180)   # waits for credentials to arrive
        out_amt = rA["amount"]
        log(f"outputs registered (B had pool credentials); per-output amount {out_amt} sats")

        # ---- wait until each side sees BOTH outputs over nostr ----
        outsA = wait_outputs(A, pk, PEERS, 180)
        wait_outputs(B, pk, PEERS, 180)
        all_outputs = sorted((o["address"], o["amount"]) for o in outsA)
        log(f"both peers see all {PEERS} outputs: {[a[:16] for a,_ in all_outputs]}")

        # ---- each peer builds its 1-input PSBT, signs via SeedSigner, registers input ----
        for base, peer, utxo in ((A, pA, uA), (B, pB, uB)):
            psbt = cjlib.build_unsigned(peer, utxo, all_outputs)
            signed_b64 = cjlib.sign_via_seedsigner(psbt, peer)   # SeedSigner code path
            requests.post(f"{base}/pool/register-input",
                          json={"public_key": pk, "psbt": signed_b64}, timeout=30)
            log(f"{peer['tag']}: signed via SeedSigner + registered input over nostr")

        # ---- a monitor (either daemon) combines + broadcasts; poll history ----
        deadline = time.time() + 180
        txid = None
        while time.time() < deadline and not txid:
            for base in (A, B):
                h = requests.get(f"{base}/history", timeout=5).json()
                items = h if isinstance(h, list) else h.get("history", [])
                if items:
                    txid = items[0].get("txid"); break
            if txid: break
            time.sleep(4)
        if not txid:
            raise RuntimeError("no broadcast recorded; check /tmp/joinstrd-*.log")

        log(f"CoinJoin broadcast over nostr! txid {txid}")
        bh = json.loads(cjlib.cli("generatetoaddress", "1", cjlib.cli("getnewaddress", wallet="peerA")))
        tx = json.loads(cjlib.cli("getrawtransaction", txid, "true", bh[0]))
        print(f"\n== LIVE NOSTR COINJOIN CONFIRMED: {len(tx['vin'])} in, {len(tx['vout'])} out, "
              f"confs={tx.get('confirmations',0)} ==")
        for v in tx["vout"]:
            print(f"   out {v['scriptPubKey']['address']}  {int(round(v['value']*1e8))} sats")
    finally:
        for p in procs:
            try: p.send_signal(signal.SIGTERM)
            except Exception: pass


if __name__ == "__main__":
    main()
