#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from nintendo_sim.nes import NES


@dataclass
class TestResult:
    rom: Path
    protocol: str
    status: int
    message: str
    frames: int
    instructions: int

    @property
    def passed(self) -> bool:
        if self.protocol == "blargg":
            return self.status == 0
        if self.protocol == "f8":
            return self.status == 1
        if self.protocol == "f0":
            return self.status == 1
        if self.protocol == "cpu_timing":
            return self.status == 1
        return False


def _read_ascii(nes: NES, start_addr: int, limit: int = 512) -> str:
    chars: list[str] = []
    for i in range(limit):
        value = nes.bus.cpu_read(start_addr + i)
        if value == 0:
            break
        if 32 <= value <= 126 or value in (10, 13, 9):
            chars.append(chr(value))
    return "".join(chars).strip()


def run_test_rom(rom_path: Path, max_instructions: int = 5_000_000, ppu_backend: str = "auto") -> TestResult:
    nes = NES.from_rom(rom_path, ppu_backend=ppu_backend)
    status = 0xFF
    message = ""
    frames = 0
    last_pc = nes.bus.cpu.pc
    stable_pc = 0
    for instruction in range(1, max_instructions + 1):
        nes.step_instruction()
        if nes.bus.ppu.frame_complete:
            frames += 1
            nes.bus.ppu.frame_complete = False

        pc = nes.bus.cpu.pc
        if pc == last_pc:
            stable_pc += 1
        else:
            stable_pc = 0
            last_pc = pc

        # blargg protocol at $6000-$6004
        signature_ok = (
            nes.bus.cpu_read(0x6001) == 0xDE and nes.bus.cpu_read(0x6002) == 0xB0 and nes.bus.cpu_read(0x6003) == 0x61
        )
        if signature_ok:
            status = nes.bus.cpu_read(0x6000)
            message = _read_ascii(nes, 0x6004)
            if status not in (0x80, 0x81):
                return TestResult(
                    rom=rom_path,
                    protocol="blargg",
                    status=status,
                    message=message,
                    frames=frames,
                    instructions=instruction,
                )

        # Validation-runtime protocol where final result is in low RAM ($F8) and code loops forever.
        f8_status = nes.bus.cpu_read(0x00F8)
        if f8_status != 0 and stable_pc > 2000:
            return TestResult(
                rom=rom_path,
                protocol="f8",
                status=f8_status,
                message="",
                frames=frames,
                instructions=instruction,
            )

        # blargg_ppu_tests_2005.09.15b protocol where result is in $F0.
        f0_status = nes.bus.cpu_read(0x00F0)
        if (
            stable_pc > 4000
            and nes.bus.ppu.ctrl == 0
            and 1 <= f0_status <= 0x20
            and all(nes.bus.cpu_read(a) == 0 for a in range(0x00F1, 0x00F9))
        ):
            return TestResult(
                rom=rom_path,
                protocol="f0",
                status=f0_status,
                message="",
                frames=frames,
                instructions=instruction,
            )

        # cpu_timing_test6 writes final text to console then loops forever at EA5A.
        if rom_path.name == "cpu_timing_test.nes" and stable_pc > 2000 and pc == 0xEA5A:
            msg_ptr = nes.bus.cpu_read(0x0000) | (nes.bus.cpu_read(0x0001) << 8)
            final_text = _read_ascii(nes, msg_ptr, limit=16).upper()
            status = 1 if final_text.startswith("PASSED") else 2
            return TestResult(
                rom=rom_path,
                protocol="cpu_timing",
                status=status,
                message=final_text,
                frames=frames,
                instructions=instruction,
            )

    return TestResult(
        rom=rom_path,
        protocol="timeout",
        status=0xFF,
        message="Timeout waiting for final status",
        frames=frames,
        instructions=max_instructions,
    )


def _iter_nes_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.nes") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run NES test ROMs ($6000 blargg + $F8 runtime + $F0 blargg_ppu + cpu_timing_test6)"
    )
    parser.add_argument("path", type=Path, help="ROM file or directory")
    parser.add_argument("--max-instructions", type=int, default=5_000_000, help="Instruction timeout per ROM")
    parser.add_argument(
        "--ppu-backend",
        choices=("auto", "python", "cython"),
        default="auto",
        help="PPU implementation backend",
    )
    args = parser.parse_args()

    roms = _iter_nes_files(args.path)
    if not roms:
        print(f"No ROM files found under {args.path}")
        return 1

    failed = 0
    for rom in roms:
        result = run_test_rom(rom, args.max_instructions, ppu_backend=args.ppu_backend)
        status = "PASS" if result.passed else "FAIL"
        print(
            f"{status:4} [{result.protocol}] {rom} "
            f"frames={result.frames} instr={result.instructions} code=0x{result.status:02X}"
        )
        if result.message:
            print(result.message)
        if not result.passed:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
