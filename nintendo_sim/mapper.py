from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


MIRROR_HORIZONTAL = "horizontal"
MIRROR_VERTICAL = "vertical"
MIRROR_FOUR_SCREEN = "four_screen"
MIRROR_SINGLE0 = "single0"
MIRROR_SINGLE1 = "single1"


def _clip8(value: int) -> int:
    return value & 0xFF


def _clip16(value: int) -> int:
    return value & 0xFFFF


@dataclass
class Mapper:
    prg_rom: bytes
    chr_data: bytearray
    prg_ram: bytearray
    has_chr_ram: bool

    def cpu_read(self, addr: int) -> Optional[int]:
        raise NotImplementedError

    def cpu_write(self, addr: int, value: int) -> bool:
        raise NotImplementedError

    def ppu_read(self, addr: int) -> int:
        raise NotImplementedError

    def ppu_write(self, addr: int, value: int) -> bool:
        raise NotImplementedError

    def mirroring(self) -> Optional[str]:
        return None

    def clock_scanline(self) -> None:
        pass

    def irq_pending(self) -> bool:
        return False

    def clear_irq(self) -> None:
        pass


@dataclass
class Mapper0(Mapper):
    def cpu_read(self, addr: int) -> Optional[int]:
        addr = _clip16(addr)
        if 0x6000 <= addr <= 0x7FFF:
            return self.prg_ram[addr - 0x6000]
        if addr < 0x8000:
            return None
        if len(self.prg_rom) == 0x4000:
            return self.prg_rom[(addr - 0x8000) & 0x3FFF]
        return self.prg_rom[addr - 0x8000]

    def cpu_write(self, addr: int, value: int) -> bool:
        addr = _clip16(addr)
        value = _clip8(value)
        if 0x6000 <= addr <= 0x7FFF:
            self.prg_ram[addr - 0x6000] = value
            return True
        return False

    def ppu_read(self, addr: int) -> int:
        return self.chr_data[_clip16(addr) & 0x1FFF]

    def ppu_write(self, addr: int, value: int) -> bool:
        if not self.has_chr_ram:
            return False
        self.chr_data[_clip16(addr) & 0x1FFF] = _clip8(value)
        return True


@dataclass
class Mapper2(Mapper):
    prg_bank_select: int = 0

    def cpu_read(self, addr: int) -> Optional[int]:
        addr = _clip16(addr)
        if 0x6000 <= addr <= 0x7FFF:
            return self.prg_ram[addr - 0x6000]
        if addr < 0x8000:
            return None
        bank_count = max(1, len(self.prg_rom) // 0x4000)
        if addr < 0xC000:
            bank = self.prg_bank_select % bank_count
            offset = bank * 0x4000 + (addr - 0x8000)
        else:
            bank = bank_count - 1
            offset = bank * 0x4000 + (addr - 0xC000)
        return self.prg_rom[offset % len(self.prg_rom)]

    def cpu_write(self, addr: int, value: int) -> bool:
        addr = _clip16(addr)
        value = _clip8(value)
        if 0x6000 <= addr <= 0x7FFF:
            self.prg_ram[addr - 0x6000] = value
            return True
        if addr >= 0x8000:
            self.prg_bank_select = value & 0x0F
            return True
        return False

    def ppu_read(self, addr: int) -> int:
        return self.chr_data[_clip16(addr) & 0x1FFF]

    def ppu_write(self, addr: int, value: int) -> bool:
        if not self.has_chr_ram:
            return False
        self.chr_data[_clip16(addr) & 0x1FFF] = _clip8(value)
        return True


@dataclass
class Mapper1(Mapper):
    shift_register: int = 0x10
    control: int = 0x0C
    chr_bank_0: int = 0
    chr_bank_1: int = 0
    prg_bank: int = 0
    ram_disable: bool = False

    def _reset_shift(self) -> None:
        self.shift_register = 0x10
        self.control |= 0x0C

    def _commit(self, target: int, value: int) -> None:
        if target == 0:
            self.control = value & 0x1F
        elif target == 1:
            self.chr_bank_0 = value & 0x1F
        elif target == 2:
            self.chr_bank_1 = value & 0x1F
        else:
            self.prg_bank = value & 0x0F
            self.ram_disable = bool(value & 0x10)

    def _prg_bank_count(self) -> int:
        return max(1, len(self.prg_rom) // 0x4000)

    def _chr_bank_count_4k(self) -> int:
        return max(1, len(self.chr_data) // 0x1000)

    def _map_prg(self, addr: int) -> int:
        bank_count = self._prg_bank_count()
        mode = (self.control >> 2) & 0x03
        bank = self.prg_bank & 0x0F
        if mode in (0, 1):
            bank &= 0x0E
            return ((bank * 0x4000) + (addr - 0x8000)) % len(self.prg_rom)
        if mode == 2:
            if addr < 0xC000:
                return addr - 0x8000
            return ((bank % bank_count) * 0x4000 + (addr - 0xC000)) % len(self.prg_rom)
        if addr < 0xC000:
            return ((bank % bank_count) * 0x4000 + (addr - 0x8000)) % len(self.prg_rom)
        return ((bank_count - 1) * 0x4000 + (addr - 0xC000)) % len(self.prg_rom)

    def _map_chr(self, addr: int) -> int:
        addr &= 0x1FFF
        mode = (self.control >> 4) & 0x01
        chr_count = self._chr_bank_count_4k()
        if mode == 0:
            bank = (self.chr_bank_0 & 0x1E) % max(1, chr_count // 2)
            return ((bank * 0x2000) + addr) % len(self.chr_data)
        if addr < 0x1000:
            bank = self.chr_bank_0 % chr_count
            return (bank * 0x1000 + addr) % len(self.chr_data)
        bank = self.chr_bank_1 % chr_count
        return (bank * 0x1000 + (addr - 0x1000)) % len(self.chr_data)

    def cpu_read(self, addr: int) -> Optional[int]:
        addr = _clip16(addr)
        if 0x6000 <= addr <= 0x7FFF:
            if self.ram_disable:
                return 0x00
            return self.prg_ram[addr - 0x6000]
        if addr < 0x8000:
            return None
        return self.prg_rom[self._map_prg(addr)]

    def cpu_write(self, addr: int, value: int) -> bool:
        addr = _clip16(addr)
        value = _clip8(value)
        if 0x6000 <= addr <= 0x7FFF:
            if not self.ram_disable:
                self.prg_ram[addr - 0x6000] = value
            return True
        if addr < 0x8000:
            return False
        if value & 0x80:
            self._reset_shift()
            return True
        complete = self.shift_register & 1
        self.shift_register >>= 1
        self.shift_register |= (value & 1) << 4
        if complete:
            target = (addr >> 13) & 0x03
            self._commit(target, self.shift_register & 0x1F)
            self.shift_register = 0x10
        return True

    def ppu_read(self, addr: int) -> int:
        return self.chr_data[self._map_chr(addr)]

    def ppu_write(self, addr: int, value: int) -> bool:
        if not self.has_chr_ram:
            return False
        self.chr_data[self._map_chr(addr)] = _clip8(value)
        return True

    def mirroring(self) -> Optional[str]:
        mode = self.control & 0x03
        if mode == 0:
            return MIRROR_SINGLE0
        if mode == 1:
            return MIRROR_SINGLE1
        if mode == 2:
            return MIRROR_VERTICAL
        return MIRROR_HORIZONTAL


@dataclass
class Mapper4(Mapper):
    """Partial MMC3 implementation focused on IRQ + bank switching."""

    bank_select: int = 0
    bank_registers: list[int] = None  # type: ignore[assignment]
    prg_mode: int = 0
    chr_mode: int = 0
    mirroring_mode: str = MIRROR_VERTICAL
    irq_latch: int = 0
    irq_counter: int = 0
    irq_reload: bool = False
    irq_enable: bool = False
    irq_flag: bool = False

    def __post_init__(self) -> None:
        if self.bank_registers is None:
            self.bank_registers = [0] * 8

    def _prg_bank_count_8k(self) -> int:
        return max(1, len(self.prg_rom) // 0x2000)

    def _chr_bank_count_1k(self) -> int:
        return max(1, len(self.chr_data) // 0x0400)

    def _map_prg_bank(self, slot: int) -> int:
        count = self._prg_bank_count_8k()
        last = count - 1
        second_last = max(0, count - 2)
        r6 = self.bank_registers[6] % count
        r7 = self.bank_registers[7] % count
        if self.prg_mode == 0:
            table = [r6, r7, second_last, last]
        else:
            table = [second_last, r7, r6, last]
        return table[slot]

    def _map_chr_bank(self, addr: int) -> int:
        count = self._chr_bank_count_1k()
        r = self.bank_registers
        if self.chr_mode == 0:
            table = [
                (r[0] & 0xFE),
                (r[0] | 0x01),
                (r[1] & 0xFE),
                (r[1] | 0x01),
                r[2],
                r[3],
                r[4],
                r[5],
            ]
        else:
            table = [
                r[2],
                r[3],
                r[4],
                r[5],
                (r[0] & 0xFE),
                (r[0] | 0x01),
                (r[1] & 0xFE),
                (r[1] | 0x01),
            ]
        bank_1k = table[(addr & 0x1FFF) // 0x0400] % count
        return bank_1k * 0x0400 + (addr & 0x03FF)

    def cpu_read(self, addr: int) -> Optional[int]:
        addr &= 0xFFFF
        if 0x6000 <= addr <= 0x7FFF:
            return self.prg_ram[addr - 0x6000]
        if addr < 0x8000:
            return None
        slot = (addr - 0x8000) // 0x2000
        bank = self._map_prg_bank(slot)
        offset = bank * 0x2000 + (addr & 0x1FFF)
        return self.prg_rom[offset % len(self.prg_rom)]

    def cpu_write(self, addr: int, value: int) -> bool:
        addr &= 0xFFFF
        value &= 0xFF
        if 0x6000 <= addr <= 0x7FFF:
            self.prg_ram[addr - 0x6000] = value
            return True
        if addr < 0x8000:
            return False
        reg = addr & 0xE001
        if reg == 0x8000:
            self.bank_select = value & 0x07
            self.prg_mode = (value >> 6) & 1
            self.chr_mode = (value >> 7) & 1
        elif reg == 0x8001:
            self.bank_registers[self.bank_select] = value
        elif reg == 0xA000:
            self.mirroring_mode = MIRROR_HORIZONTAL if (value & 1) else MIRROR_VERTICAL
        elif reg == 0xC000:
            self.irq_latch = value
        elif reg == 0xC001:
            self.irq_reload = True
        elif reg == 0xE000:
            self.irq_enable = False
            self.irq_flag = False
        elif reg == 0xE001:
            self.irq_enable = True
        return True

    def ppu_read(self, addr: int) -> int:
        return self.chr_data[self._map_chr_bank(addr)]

    def ppu_write(self, addr: int, value: int) -> bool:
        if not self.has_chr_ram:
            return False
        self.chr_data[self._map_chr_bank(addr)] = value & 0xFF
        return True

    def clock_scanline(self) -> None:
        if self.irq_counter == 0 or self.irq_reload:
            self.irq_counter = self.irq_latch
            self.irq_reload = False
        else:
            self.irq_counter = (self.irq_counter - 1) & 0xFF
        if self.irq_counter == 0 and self.irq_enable:
            self.irq_flag = True

    def irq_pending(self) -> bool:
        return self.irq_flag

    def clear_irq(self) -> None:
        self.irq_flag = False

    def mirroring(self) -> Optional[str]:
        return self.mirroring_mode

