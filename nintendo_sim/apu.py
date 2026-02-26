from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APU:
    registers: list[int] = field(default_factory=lambda: [0] * 0x18)
    status: int = 0
    frame_counter: int = 0
    frame_irq_inhibit: bool = False
    frame_irq_flag: bool = False

    def write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if 0x4000 <= addr <= 0x4013:
            self.registers[addr - 0x4000] = value
            return
        if addr == 0x4015:
            self.status = value
            return
        if addr == 0x4017:
            self.frame_irq_inhibit = bool(value & 0x40)
            if self.frame_irq_inhibit:
                self.frame_irq_flag = False
            self.registers[addr - 0x4000] = value

    def read(self, addr: int) -> int:
        if addr == 0x4015:
            value = self.status & 0x1F
            if self.frame_irq_flag:
                value |= 0x40
            self.frame_irq_flag = False
            return value
        return 0

    def clock(self) -> None:
        self.frame_counter += 1
        if self.frame_irq_inhibit:
            return
        if self.frame_counter >= 29830:
            self.frame_counter = 0
            self.frame_irq_flag = True

    def irq_pending(self) -> bool:
        return self.frame_irq_flag and not self.frame_irq_inhibit

