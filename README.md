# Nintendo Sim (Python NES Emulator)

## Demo Recording

<video src="https://raw.githubusercontent.com/kaonashi-tyc/codex-nes-emulator/main/demo/demo.mp4" controls width="60%"></video>

If the embedded player does not render in your client:

- [Play `demo.mp4`](https://raw.githubusercontent.com/kaonashi-tyc/codex-nes-emulator/main/demo/demo.mp4)
- [Download `demo.mov`](demo/demo.mov)

This repository contains a from-scratch Python NES emulator implementation guided by `NESDoc.pdf`.

## Implemented

- 6502 CPU core (official opcodes + major undocumented opcodes)
- iNES ROM loader
- Mapper support:
  - Mapper 0 (NROM)
  - Mapper 1 (MMC1)
  - Mapper 2 (UNROM)
  - Partial Mapper 4 (MMC3)
- PPU timing/rendering loop with sprite/background composition, NMI timing, and sprite DMA
- Controller input (`$4016/$4017`)
- APU register/IRQ skeleton sufficient for CPU/PPU-focused test ROM execution

## Run Super Mario Bros

Install (recommended: use a virtual environment; builds the Cython PPU during wheel build without writing `.so` into source):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install .
```

If `pip3 install .` fails on macOS/Homebrew with `error: externally-managed-environment`, you are installing into a system-managed Python (PEP 668). Use the virtual environment steps above and run `python -m pip install .` after activation.

You can bypass the protection with:

```bash
python3 -m pip install --break-system-packages .
```

but this is not recommended because it can break your system/Homebrew Python environment.

Launch:

```bash
python run_nes.py "rom/Super Mario Bro.nes"
```

Choose PPU backend explicitly (default is `auto`):

```bash
python run_nes.py "rom/Super Mario Bro.nes" --ppu-backend cython
python run_nes.py "rom/Super Mario Bro.nes" --ppu-backend python
```

If you only want Python dependencies (no package build), you can still do:

```bash
python -m pip install -r requirements.txt
```

Note: `pip install -e .` (editable mode) may place extension artifacts in the source tree on setuptools.

Controls:

- `Z`: A
- `X`: B
- `Right Shift`: Select
- `Enter`: Start
- Arrow keys: D-pad

## Run test ROMs

Run a single test ROM:

```bash
python run_test_roms.py testsuites/other/nestest.nes
```

Run an entire folder:

```bash
python run_test_roms.py testsuites/instr_test-v5
```

Run tests against a specific PPU backend:

```bash
python run_test_roms.py testsuites/instr_test-v5 --ppu-backend cython
```
