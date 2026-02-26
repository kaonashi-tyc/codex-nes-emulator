from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mapper import (
    MIRROR_FOUR_SCREEN,
    MIRROR_HORIZONTAL,
    MIRROR_VERTICAL,
    Mapper,
    Mapper0,
    Mapper1,
    Mapper2,
    Mapper4,
)


@dataclass
class Cartridge:
    prg_rom: bytes
    chr_data: bytearray
    prg_ram: bytearray
    mapper_id: int
    mirroring: str
    has_battery: bool
    has_trainer: bool
    has_chr_ram: bool
    mapper: Mapper


def _build_mapper(mapper_id: int, prg_rom: bytes, chr_data: bytearray, prg_ram: bytearray, has_chr_ram: bool) -> Mapper:
    if mapper_id == 0:
        return Mapper0(prg_rom=prg_rom, chr_data=chr_data, prg_ram=prg_ram, has_chr_ram=has_chr_ram)
    if mapper_id == 1:
        return Mapper1(prg_rom=prg_rom, chr_data=chr_data, prg_ram=prg_ram, has_chr_ram=has_chr_ram)
    if mapper_id == 2:
        return Mapper2(prg_rom=prg_rom, chr_data=chr_data, prg_ram=prg_ram, has_chr_ram=has_chr_ram)
    if mapper_id == 4:
        return Mapper4(prg_rom=prg_rom, chr_data=chr_data, prg_ram=prg_ram, has_chr_ram=has_chr_ram)
    raise ValueError(f"Unsupported mapper: {mapper_id}")


def load_ines(path: str | Path) -> Cartridge:
    rom_path = Path(path)
    blob = rom_path.read_bytes()
    if len(blob) < 16:
        raise ValueError("ROM file too small")
    if blob[:4] != b"NES\x1A":
        raise ValueError("Invalid iNES header signature")

    prg_rom_banks = blob[4]
    chr_rom_banks = blob[5]
    flag6 = blob[6]
    flag7 = blob[7]
    prg_ram_banks = blob[8] if len(blob) > 8 else 0

    mapper_low = flag6 >> 4
    mapper_high = flag7 & 0xF0
    mapper_id = mapper_high | mapper_low

    has_trainer = bool(flag6 & 0x04)
    has_battery = bool(flag6 & 0x02)
    four_screen = bool(flag6 & 0x08)
    vertical_mirror = bool(flag6 & 0x01)

    if four_screen:
        mirroring = MIRROR_FOUR_SCREEN
    else:
        mirroring = MIRROR_VERTICAL if vertical_mirror else MIRROR_HORIZONTAL

    offset = 16
    if has_trainer:
        if len(blob) < offset + 512:
            raise ValueError("ROM missing trainer data")
        offset += 512

    prg_size = prg_rom_banks * 0x4000
    chr_size = chr_rom_banks * 0x2000
    if len(blob) < offset + prg_size + chr_size:
        raise ValueError("ROM is truncated")

    prg_rom = blob[offset : offset + prg_size]
    offset += prg_size
    if chr_size:
        chr_data = bytearray(blob[offset : offset + chr_size])
        has_chr_ram = False
    else:
        chr_data = bytearray(0x2000)
        has_chr_ram = True

    ram_size = max(1, prg_ram_banks) * 0x2000
    prg_ram = bytearray(ram_size)
    mapper = _build_mapper(mapper_id, prg_rom, chr_data, prg_ram, has_chr_ram)

    return Cartridge(
        prg_rom=prg_rom,
        chr_data=chr_data,
        prg_ram=prg_ram,
        mapper_id=mapper_id,
        mirroring=mirroring,
        has_battery=has_battery,
        has_trainer=has_trainer,
        has_chr_ram=has_chr_ram,
        mapper=mapper,
    )

