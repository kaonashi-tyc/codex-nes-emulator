# Nintendo Sim (Python NES Emulator)

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

Install dependencies:

```bash
pip install -r requirements.txt
```

Launch:

```bash
python run_nes.py "rom/Super Mario Bro.nes"
```

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

