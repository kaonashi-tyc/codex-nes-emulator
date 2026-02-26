from __future__ import annotations

from dataclasses import dataclass, field

from .apu import APU
from .controller import Controller
from .cpu import CPU6502
from .ppu import PPU
from .rom import Cartridge


@dataclass
class Bus:
    cartridge: Cartridge
    cpu_ram: bytearray = field(default_factory=lambda: bytearray(2048))
    controller1: Controller = field(default_factory=Controller)
    controller2: Controller = field(default_factory=Controller)

    def __post_init__(self) -> None:
        self.apu = APU()
        self.ppu = PPU(self.cartridge)
        self.cpu = CPU6502(self.cpu_read, self.cpu_write)
        self.system_clock_counter = 0

    def cpu_read(self, addr: int) -> int:
        addr &= 0xFFFF
        mapped = self.cartridge.mapper.cpu_read(addr)
        if mapped is not None:
            return mapped & 0xFF

        if addr <= 0x1FFF:
            return self.cpu_ram[addr & 0x07FF]
        if 0x2000 <= addr <= 0x3FFF:
            return self.ppu.cpu_read(addr & 0x0007)
        if addr == 0x4015:
            return self.apu.read(addr)
        if addr == 0x4016:
            return self.controller1.read()
        if addr == 0x4017:
            return self.controller2.read()
        return 0x00

    def _dma_transfer(self, page: int) -> None:
        start = (page & 0xFF) << 8
        block = bytes(self.cpu_read(start + i) for i in range(256))
        self.ppu.dma_write(start, block)
        self.cpu.stall_cycles += 513 + (self.cpu.total_cycles & 1)

    def cpu_write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if self.cartridge.mapper.cpu_write(addr, value):
            return

        if addr <= 0x1FFF:
            self.cpu_ram[addr & 0x07FF] = value
            return
        if 0x2000 <= addr <= 0x3FFF:
            self.ppu.cpu_write(addr & 0x0007, value)
            return
        if 0x4000 <= addr <= 0x4013:
            self.apu.write(addr, value)
            return
        if addr == 0x4014:
            self._dma_transfer(value)
            return
        if addr == 0x4015:
            self.apu.write(addr, value)
            return
        if addr == 0x4016:
            self.controller1.write(value)
            self.controller2.write(value)
            return
        if addr == 0x4017:
            self.apu.write(addr, value)

    def clock_cpu_cycles(self, cpu_cycles: int) -> None:
        apu_clock = self.apu.clock
        apu_irq_pending = self.apu.irq_pending
        ppu = self.ppu
        ppu_clock = ppu.clock
        mapper_irq_pending = self.cartridge.mapper.irq_pending
        cpu_request_nmi = self.cpu.request_nmi
        cpu_request_irq = self.cpu.request_irq
        system_clock_counter = self.system_clock_counter

        for _ in range(cpu_cycles):
            apu_clock()

            ppu_clock()
            if ppu.nmi:
                ppu.nmi = False
                cpu_request_nmi()
            ppu_clock()
            if ppu.nmi:
                ppu.nmi = False
                cpu_request_nmi()
            ppu_clock()
            if ppu.nmi:
                ppu.nmi = False
                cpu_request_nmi()

            if apu_irq_pending() or mapper_irq_pending():
                cpu_request_irq()
            system_clock_counter += 1

        self.system_clock_counter = system_clock_counter

    def step(self) -> int:
        cycles = self.cpu.step()
        self.clock_cpu_cycles(cycles)
        return cycles

    def reset(self) -> None:
        self.cpu_ram = bytearray(2048)
        self.ppu.reset()
        self.cpu.reset()
        self.system_clock_counter = 0
