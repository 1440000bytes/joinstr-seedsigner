#!/usr/bin/env python3
"""
Pre-load a real joinstr coinjoin PSBT + signing seed into the SeedSigner emulator and
start at seed selection, so the GUI walks Select seed -> CoinJoin verification -> Sign
-> signed-PSBT QR. Reads /tmp/joinstr_demo_psbt.txt and /tmp/joinstr_demo_seed.txt
(written by prep_demo_psbt.py). Button presses come from xdotool (see record_demo.sh).
"""
import os, sys, base64, types
UP = "/home/test/joinstr-seedsigner/emulator/upstream"
sys.path.insert(0, "/home/test/joinstr-seedsigner")
sys.path.insert(0, os.path.join(UP, "src"))

# stub picamera so the controller's warm-up import of pivideostream doesn't spew
_pc = types.ModuleType("picamera"); _pca = types.ModuleType("picamera.array")
_pca.PiRGBArray = object; _pc.PiCamera = object; _pc.array = _pca
sys.modules.setdefault("picamera", _pc); sys.modules.setdefault("picamera.array", _pca)

from embit.psbt import PSBT

# skip the multi-second opening splash animation (blocks the flow start)
import seedsigner.views.screensaver as _ss
_ss.OpeningSplashView.run = lambda self: None

# log every view transition so record_demo.sh timing can be tuned
import seedsigner.views.view as _vmod
_orig_run = _vmod.Destination.run
def _logged_run(self, *a, **k):
    try: print(f"[view] {self.View_cls.__name__}", flush=True)
    except Exception: pass
    return _orig_run(self, *a, **k)
_vmod.Destination.run = _logged_run

from seedsigner.controller import Controller
from seedsigner.models.seed import Seed
from seedsigner.models.settings_definition import SettingsConstants
from seedsigner.views.view import Destination
from seedsigner.views.psbt_views import PSBTSelectSeedView

mnemonic = open("/tmp/joinstr_demo_seed.txt").read().strip()
psbt_b64 = open("/tmp/joinstr_demo_psbt.txt").read().strip()

controller = Controller.get_instance()
controller.settings.set_value(SettingsConstants.SETTING__NETWORK, SettingsConstants.REGTEST)
controller.storage.seeds.append(Seed(mnemonic=mnemonic.split()))

# pre-load the PSBT exactly as ScanView would, then jump to seed selection
controller.psbt = PSBT.parse(base64.b64decode(psbt_b64))
controller.psbt_parser = None
controller.psbt_seed = None

try:
    controller.start(initial_destination=Destination(PSBTSelectSeedView))
except IndexError:
    pass   # back_stack underflow when the flow returns home (we started mid-flow)
