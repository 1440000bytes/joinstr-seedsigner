# joinstr-seedsigner

Sign [joinstr](https://gitlab.com/invincible-privacy/joinstr) coinjoins with a [SeedSigner](https://github.com/SeedSigner/seedsigner) air-gapped signer, driven on the desktop [SeedSigner emulator](https://github.com/enteropositivo/seedsigner-emulator).

joinstr's `joinstrd` daemon does all the networked work (nostr, Tor, Bitcoin Core, PSBT combine/finalize). SeedSigner only verifies and signs the coinjoin PSBT. Its `POST /pool/register-input` already takes an *already-signed* PSBT, so SeedSigner drops in where a hot wallet used to sign, with no changes to joinstr.

The glue here builds each peer's single-input PSBT (1 input, all participants' equal-value outputs, `SIGHASH_ALL|ANYONECANPAY`), signs it through SeedSigner's code, and feeds it back to the daemon. A small patch adds a coinjoin-aware verification screen to SeedSigner.

## Requirements

- Python 3.10
- Bitcoin Core (`bitcoind`/`bitcoin-cli`), used on regtest
- Tor with a SOCKS proxy on `127.0.0.1:9050`
- Python: `embit fastapi uvicorn pydantic "requests[socks]" nostr urtypes Pillow qrcode pyzbar opencv-python-headless`
- For the emulator GUI / video: `python3-tk xvfb libzbar0 imagemagick ffmpeg xdotool`

## Setup

```sh
git clone https://gitlab.com/invincible-privacy/joinstr.git
git clone https://github.com/SeedSigner/seedsigner.git
git clone https://github.com/enteropositivo/seedsigner-emulator.git

# overlay the emulator shims onto SeedSigner
rsync -a seedsigner-emulator/seedsigner/ seedsigner/src/seedsigner/

# apply the coinjoin patch (sighash, coinjoin parser + verification view, pyzbar compat)
cd seedsigner && git apply ../joinstr-seedsigner/patches/seedsigner-coinjoin.patch && cd ..
```

The live emulator GUI (`record_demo.sh`, `run_emulator_shot.sh`, interactive `emulator_demo.py`) also needs two one-line compat edits to the emulator overlay files. These are not needed for the coinjoin demos (`demo_coinjoin.py`, `nostr_coinjoin.py`, `run_demo.sh`) or the PNG render (`screenshot_coinjoin.py`):

- `seedsigner/src/seedsigner/gui/renderer.py`: add `is_screenshot_generator = False` to the `Renderer` class.
- `seedsigner/src/seedsigner/hardware/camera.py`: add `class CameraConnectionError(Exception): pass`.

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
```
