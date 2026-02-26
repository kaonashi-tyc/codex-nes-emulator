# Nintendo Sim (Python NES Emulator)

## Demo

<img src="demo/demo.gif" alt="NES gameplay demo" width="60%">

This repository contains a from-scratch Python NES emulator implementation guided by `NESDoc.pdf`.

## How It Was Built

This emulator was built mostly from scratch with the Codex app (GPT 5.3 Codex, xhigh).

### Step 1: Research
I asked Codex to find test suites and developer documentation (including `NESDoc.pdf`) and save them locally. Codex was explicitly told not to look at other emulator implementations.

### Step 2: Implementation
Codex iterated on the emulator until the test suites passed. This took multiple prompts, but most of them were simply “continue”.

### Step 3: Optimization
The first Python implementation was too slow, so with some manual guidance I profiled it (flamegraph) and asked Codex to rewrite the PPU in Cython using pre-allocation to speed up rendering.

The whole thing took about 1 hour and around 2% of my weekly usage as a Pro subscriber.

## What is Implemented

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
