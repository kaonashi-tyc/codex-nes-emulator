from pathlib import Path
import time
import os
from nintendo_sim.nes import NES

ROM = Path('rom/Super Mario Bro.nes')
FRAMES = int(os.environ.get("FRAMES", "240"))

nes = NES.from_rom(ROM)
start = time.time()
for _ in range(FRAMES):
    nes.step_frame(copy_frame=False)
elapsed = time.time() - start
print(f"frames={FRAMES} elapsed={elapsed:.3f}s fps={FRAMES/elapsed:.3f}")
