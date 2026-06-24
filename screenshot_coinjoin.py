#!/usr/bin/env python3
"""
Render the real SeedSigner coinjoin verification screen to PNG using SeedSigner's
own ScreenshotRenderer (no Tkinter window needed). Feeds it a genuine 2-peer
joinstr PSBT so the on-device figures are real.
"""
import os, sys
from unittest.mock import Mock

UP = "/home/test/joinstr-seedsigner/emulator/upstream"
sys.path.insert(0, "/home/test/joinstr-seedsigner")
sys.path.insert(0, os.path.join(UP, "src"))
sys.path.insert(0, os.path.join(UP, "tests"))

import cjlib
from seedsigner.gui.renderer import Renderer
from screenshot_generator.utils import ScreenshotRenderer, ScreenshotComplete

# --- patch ScreenshotRenderer over the normal Renderer (no hardware/Tk) ---
ScreenshotRenderer.configure_instance()
screenshot_renderer = ScreenshotRenderer.get_instance()
Renderer.configure_instance = Mock()
Renderer.get_instance = Mock(return_value=screenshot_renderer)

OUT = "/home/test/joinstr-seedsigner/screenshots"
screenshot_renderer.set_screenshot_path(OUT)

from seedsigner.controller import Controller
from seedsigner.models.settings import Settings
from seedsigner.models.settings_definition import SettingsConstants
from seedsigner.models.seed import Seed
from seedsigner.models.psbt_parser import PSBTParser
from seedsigner.views import psbt_views

Controller.reset_instance()
controller = Controller.get_instance()
controller.settings.set_value(SettingsConstants.SETTING__NETWORK, SettingsConstants.REGTEST)

# --- build a genuine 2-peer joinstr coinjoin PSBT (peer-1's single-input form) ---
DENOM, FEE = 90_000, 1_000
OUT_AMT = DENOM - FEE
p1, p2 = cjlib.mk_peer("shot-peerA"), cjlib.mk_peer("shot-peerB")
u1 = cjlib.fund(p1, DENOM + 5_000)
o1 = cjlib.fresh_output_addr(p1, 7)
o2 = cjlib.fresh_output_addr(p2, 9)
all_outputs = sorted([(o1, OUT_AMT), (o2, OUT_AMT)])
psbt1 = cjlib.build_unsigned(p1, u1, all_outputs, my_out_index=7)

seed1 = Seed(mnemonic=p1["mnemonic"].split())
parser = PSBTParser(psbt1, seed1, network=SettingsConstants.REGTEST)
assert parser.is_coinjoin, "not detected as coinjoin"

# wire the controller state the View reads
controller.psbt = psbt1
controller.psbt_seed = seed1
controller.psbt_parser = parser

# --- render the coinjoin verification View to PNG ---
screenshot_renderer.set_screenshot_filename("PSBTCoinjoinOverviewView.png")
try:
    psbt_views.PSBTCoinjoinOverviewView().run()
except ScreenshotComplete:
    pass

path = os.path.join(OUT, "PSBTCoinjoinOverviewView.png")
print(f"coinjoin summary: {parser.coinjoin_summary}")
print(f"screenshot saved: {path}  ({os.path.getsize(path)} bytes)")
