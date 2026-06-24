# joinstr-seedsigner

Sign [joinstr](https://gitlab.com/1440000bytes/joinstr) coinjoins with a [SeedSigner](https://github.com/SeedSigner/seedsigner) air-gapped signer, driven on the desktop [SeedSigner emulator](https://github.com/enteropositivo/seedsigner-emulator).

joinstr's `joinstrd` daemon does all the networked work (nostr, Tor, Bitcoin Core, PSBT combine/finalize). SeedSigner only verifies and signs the coinjoin PSBT. Its `POST /pool/register-input` already takes an *already-signed* PSBT, so SeedSigner drops in where a hot wallet used to sign — no changes to joinstr.

The glue here builds each peer's single-input PSBT (1 input, all participants' equal-value outputs, `SIGHASH_ALL|ANYONECANPAY`), signs it through SeedSigner's code, and feeds it back to the daemon. A small patch adds a coinjoin-aware verification screen to SeedSigner.

## Requirements

- Python 3.10
- Bitcoin Core (`bitcoind`/`bitcoin-cli`) — used on regtest
- Tor with a SOCKS proxy on `127.0.0.1:9050`
- Python: `embit fastapi uvicorn pydantic "requests[socks]" nostr urtypes Pillow qrcode pyzbar opencv-python-headless`
- For the emulator GUI / video: `python3-tk xvfb libzbar0 imagemagick ffmpeg xdotool`

## Setup

```sh
git clone https://gitlab.com/1440000bytes/joinstr.git
git clone https://github.com/SeedSigner/seedsigner.git
git clone https://github.com/enteropositivo/seedsigner-emulator.git

# overlay the emulator shims onto SeedSigner
rsync -a seedsigner-emulator/seedsigner/ seedsigner/src/seedsigner/

# apply the coinjoin patch (sighash, coinjoin parser + verification view, pyzbar compat)
cd seedsigner && git apply ../joinstr-seedsigner/patches/seedsigner-coinjoin.patch && cd ..
```

Two one-line compat edits the patch can't carry (they touch emulator overlay files):

- `seedsigner/src/seedsigner/gui/renderer.py` — add `is_screenshot_generator = False` to the `Renderer` class.
- `seedsigner/src/seedsigner/hardware/camera.py` — add `class CameraConnectionError(Exception): pass`.

Configure `joinstrd` (`~/.joinstr/config.ini`) with your regtest RPC, a nostr relay, and the Tor proxy. Paths in the scripts assume the layout under `/home/test/joinstr-seedsigner`; adjust if you clone elsewhere.

## Usage

```sh
# offline end-to-end: 2-peer coinjoin signed through SeedSigner's code, broadcast on regtest
python3 demo_coinjoin.py

# live: a real 2-peer pool over nostr via two joinstrd instances, then broadcast
python3 nostr_coinjoin.py
# or the one-shot wrapper that also funds regtest and renders the device screen:
bash run_demo.sh

# render just the coinjoin verification screen to a PNG (SeedSigner's own renderer)
python3 screenshot_coinjoin.py

# record a video of the emulator window signing a coinjoin -> demo.mp4
bash record_demo.sh
```

## Trade-offs / TODO

- **Not for mainnet.** Regtest only. joinstr itself is experimental.
- The live demo uses a public relay (`nos.lol`) over Tor; relay propagation makes timing variable. A joiner must retry `register-output` until its pool credentials arrive over DM.
- The video demo **pre-loads** the PSBT rather than camera-scanning a QR in the window. Camera-frame injection into the live Tk scan screen was flaky (threading/format); hardening it is the main TODO for a fully hands-on demo.
- "My output" identification needs the companion to annotate the user's own coinjoin output with its bip32 derivation; without it the device shows the figures but can't single out the user's output.
- The emulator overlay lags upstream SeedSigner; the compat edits above (renderer, camera) and the pyzbar `binary=` change exist only because of that drift.
- joinstr bug noticed: `joinstrd.py` logs the wtxid as the "Finalized Transaction ID" (the broadcast txid is correct).
- `xvfb`/`ffmpeg` need a real display or a non-sandboxed environment; `x11grab`'s offset didn't match the Tk window position, so frames are grabbed with `import -window`.
