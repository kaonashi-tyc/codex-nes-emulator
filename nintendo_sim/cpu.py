from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


FLAG_C = 1 << 0
FLAG_Z = 1 << 1
FLAG_I = 1 << 2
FLAG_D = 1 << 3
FLAG_B = 1 << 4
FLAG_U = 1 << 5
FLAG_V = 1 << 6
FLAG_N = 1 << 7


AddressMode = Callable[[], None]
Operation = Callable[[], int]


@dataclass
class Instruction:
    name: str
    mode: AddressMode
    operate: Operation
    cycles: int
    page_cycle: bool = False


class CPU6502:
    def __init__(self, read: Callable[[int], int], write: Callable[[int, int], None]) -> None:
        self._read = read
        self._write = write

        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.pc = 0
        self.p = FLAG_U | FLAG_I

        self.addr_abs = 0
        self.addr_base = 0
        self.addr_rel = 0
        self.fetched = 0
        self.page_crossed = False
        self.current_mode: AddressMode = self._IMP
        self.halted = False

        self.total_cycles = 0
        self.stall_cycles = 0
        self.requested_nmi = False
        self.requested_irq = False

        self.lookup = [Instruction("NOP", self._IMP, self._NOP, 2) for _ in range(256)]
        self._build_lookup()

    def _clip8(self, value: int) -> int:
        return value & 0xFF

    def _clip16(self, value: int) -> int:
        return value & 0xFFFF

    def _read16(self, addr: int) -> int:
        lo = self._read(addr & 0xFFFF)
        hi = self._read((addr + 1) & 0xFFFF)
        return (hi << 8) | lo

    def _push(self, value: int) -> None:
        self._write(0x0100 + self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def _pull(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self._read(0x0100 + self.sp)

    def _set_flag(self, flag: int, value: bool) -> None:
        if value:
            self.p |= flag
        else:
            self.p &= ~flag
        self.p |= FLAG_U
        self.p &= 0xFF

    def _get_flag(self, flag: int) -> int:
        return 1 if (self.p & flag) else 0

    def _set_zn(self, value: int) -> None:
        value &= 0xFF
        self._set_flag(FLAG_Z, value == 0)
        self._set_flag(FLAG_N, bool(value & 0x80))

    def reset(self) -> None:
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.p = FLAG_U | FLAG_I
        self.addr_abs = 0
        self.addr_base = 0
        self.addr_rel = 0
        self.fetched = 0
        self.page_crossed = False
        self.halted = False
        self.stall_cycles = 0
        self.requested_nmi = False
        self.requested_irq = False
        self.pc = self._read16(0xFFFC)
        self.total_cycles = 7

    def request_nmi(self) -> None:
        self.requested_nmi = True

    def request_irq(self) -> None:
        self.requested_irq = True

    def _service_interrupt(self, vector: int, is_brk: bool = False) -> int:
        self._push((self.pc >> 8) & 0xFF)
        self._push(self.pc & 0xFF)
        status = self.p
        status |= FLAG_U
        if is_brk:
            status |= FLAG_B
        else:
            status &= ~FLAG_B
        self._push(status)
        self._set_flag(FLAG_I, True)
        self.pc = self._read16(vector)
        return 7

    def step(self) -> int:
        if self.halted:
            self.total_cycles += 1
            return 1

        if self.stall_cycles > 0:
            self.stall_cycles -= 1
            self.total_cycles += 1
            return 1

        if self.requested_nmi:
            self.requested_nmi = False
            cycles = self._service_interrupt(0xFFFA, is_brk=False)
            self.total_cycles += cycles
            return cycles

        if self.requested_irq and not self._get_flag(FLAG_I):
            self.requested_irq = False
            cycles = self._service_interrupt(0xFFFE, is_brk=False)
            self.total_cycles += cycles
            return cycles
        self.requested_irq = False

        opcode = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF

        instruction = self.lookup[opcode]
        self.current_mode = instruction.mode
        self.page_crossed = False
        instruction.mode()
        extra = instruction.operate()
        cycles = instruction.cycles + extra + (1 if instruction.page_cycle and self.page_crossed else 0)
        self.total_cycles += cycles
        return cycles

    def _fetch(self) -> int:
        if self.current_mode not in (self._IMP, self._ACC):
            self.fetched = self._read(self.addr_abs)
        return self.fetched

    # Addressing modes
    def _IMP(self) -> None:
        self.fetched = self.a

    def _ACC(self) -> None:
        self.fetched = self.a

    def _IMM(self) -> None:
        self.addr_abs = self.pc
        self.pc = (self.pc + 1) & 0xFFFF

    def _ZP0(self) -> None:
        self.addr_abs = self._read(self.pc) & 0x00FF
        self.pc = (self.pc + 1) & 0xFFFF

    def _ZPX(self) -> None:
        self.addr_abs = (self._read(self.pc) + self.x) & 0x00FF
        self.pc = (self.pc + 1) & 0xFFFF

    def _ZPY(self) -> None:
        self.addr_abs = (self._read(self.pc) + self.y) & 0x00FF
        self.pc = (self.pc + 1) & 0xFFFF

    def _REL(self) -> None:
        value = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        if value & 0x80:
            value -= 0x100
        self.addr_rel = value

    def _ABS(self) -> None:
        lo = self._read(self.pc)
        hi = self._read((self.pc + 1) & 0xFFFF)
        self.addr_base = (hi << 8) | lo
        self.addr_abs = self.addr_base
        self.pc = (self.pc + 2) & 0xFFFF

    def _ABX(self) -> None:
        lo = self._read(self.pc)
        hi = self._read((self.pc + 1) & 0xFFFF)
        self.addr_base = (hi << 8) | lo
        self.addr_abs = (self.addr_base + self.x) & 0xFFFF
        self.page_crossed = (self.addr_abs & 0xFF00) != (self.addr_base & 0xFF00)
        self.pc = (self.pc + 2) & 0xFFFF

    def _ABY(self) -> None:
        lo = self._read(self.pc)
        hi = self._read((self.pc + 1) & 0xFFFF)
        self.addr_base = (hi << 8) | lo
        self.addr_abs = (self.addr_base + self.y) & 0xFFFF
        self.page_crossed = (self.addr_abs & 0xFF00) != (self.addr_base & 0xFF00)
        self.pc = (self.pc + 2) & 0xFFFF

    def _IND(self) -> None:
        ptr_lo = self._read(self.pc)
        ptr_hi = self._read((self.pc + 1) & 0xFFFF)
        self.pc = (self.pc + 2) & 0xFFFF
        ptr = (ptr_hi << 8) | ptr_lo
        if ptr_lo == 0xFF:
            lo = self._read(ptr)
            hi = self._read(ptr & 0xFF00)
        else:
            lo = self._read(ptr)
            hi = self._read((ptr + 1) & 0xFFFF)
        self.addr_abs = (hi << 8) | lo

    def _IZX(self) -> None:
        t = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        lo = self._read((t + self.x) & 0x00FF)
        hi = self._read((t + self.x + 1) & 0x00FF)
        self.addr_abs = (hi << 8) | lo

    def _IZY(self) -> None:
        t = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        lo = self._read(t & 0x00FF)
        hi = self._read((t + 1) & 0x00FF)
        self.addr_base = (hi << 8) | lo
        self.addr_abs = (self.addr_base + self.y) & 0xFFFF
        self.page_crossed = (self.addr_abs & 0xFF00) != (self.addr_base & 0xFF00)

    # Operations
    def _ADC_value(self, value: int) -> None:
        temp = self.a + value + self._get_flag(FLAG_C)
        self._set_flag(FLAG_C, temp > 0xFF)
        result = temp & 0xFF
        self._set_flag(FLAG_V, bool((~(self.a ^ value) & (self.a ^ result)) & 0x80))
        self.a = result
        self._set_zn(self.a)

    def _SBC_value(self, value: int) -> None:
        value ^= 0xFF
        temp = self.a + value + self._get_flag(FLAG_C)
        self._set_flag(FLAG_C, temp > 0xFF)
        result = temp & 0xFF
        self._set_flag(FLAG_V, bool(((temp ^ self.a) & (temp ^ value)) & 0x80))
        self.a = result
        self._set_zn(self.a)

    def _branch(self, condition: bool) -> int:
        if not condition:
            return 0
        old_pc = self.pc
        self.pc = (self.pc + self.addr_rel) & 0xFFFF
        if (old_pc & 0xFF00) != (self.pc & 0xFF00):
            return 2
        return 1

    def _ORA(self) -> int:
        self.a |= self._fetch()
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _AND(self) -> int:
        self.a &= self._fetch()
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _EOR(self) -> int:
        self.a ^= self._fetch()
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _ADC(self) -> int:
        self._ADC_value(self._fetch())
        return 0

    def _SBC(self) -> int:
        self._SBC_value(self._fetch())
        return 0

    def _CMP(self) -> int:
        value = self._fetch()
        temp = (self.a - value) & 0x1FF
        self._set_flag(FLAG_C, self.a >= value)
        self._set_zn(temp & 0xFF)
        return 0

    def _CPX(self) -> int:
        value = self._fetch()
        temp = (self.x - value) & 0x1FF
        self._set_flag(FLAG_C, self.x >= value)
        self._set_zn(temp & 0xFF)
        return 0

    def _CPY(self) -> int:
        value = self._fetch()
        temp = (self.y - value) & 0x1FF
        self._set_flag(FLAG_C, self.y >= value)
        self._set_zn(temp & 0xFF)
        return 0

    def _BIT(self) -> int:
        value = self._fetch()
        self._set_flag(FLAG_Z, (self.a & value) == 0)
        self._set_flag(FLAG_N, bool(value & 0x80))
        self._set_flag(FLAG_V, bool(value & 0x40))
        return 0

    def _ASL(self) -> int:
        if self.current_mode == self._ACC:
            value = self.a
            self._set_flag(FLAG_C, bool(value & 0x80))
            self.a = (value << 1) & 0xFF
            self._set_zn(self.a)
            return 0
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x80))
        value = (value << 1) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _LSR(self) -> int:
        if self.current_mode == self._ACC:
            value = self.a
            self._set_flag(FLAG_C, bool(value & 0x01))
            self.a = (value >> 1) & 0xFF
            self._set_zn(self.a)
            return 0
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x01))
        value = (value >> 1) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _ROL(self) -> int:
        carry = self._get_flag(FLAG_C)
        if self.current_mode == self._ACC:
            value = self.a
            self._set_flag(FLAG_C, bool(value & 0x80))
            self.a = ((value << 1) | carry) & 0xFF
            self._set_zn(self.a)
            return 0
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x80))
        value = ((value << 1) | carry) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _ROR(self) -> int:
        carry = self._get_flag(FLAG_C)
        if self.current_mode == self._ACC:
            value = self.a
            self._set_flag(FLAG_C, bool(value & 0x01))
            self.a = ((carry << 7) | (value >> 1)) & 0xFF
            self._set_zn(self.a)
            return 0
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x01))
        value = ((carry << 7) | (value >> 1)) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _INC(self) -> int:
        value = (self._read(self.addr_abs) + 1) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _DEC(self) -> int:
        value = (self._read(self.addr_abs) - 1) & 0xFF
        self._write(self.addr_abs, value)
        self._set_zn(value)
        return 0

    def _LDA(self) -> int:
        self.a = self._fetch() & 0xFF
        self._set_zn(self.a)
        return 0

    def _LDX(self) -> int:
        self.x = self._fetch() & 0xFF
        self._set_zn(self.x)
        return 0

    def _LDY(self) -> int:
        self.y = self._fetch() & 0xFF
        self._set_zn(self.y)
        return 0

    def _STA(self) -> int:
        self._write(self.addr_abs, self.a)
        return 0

    def _STX(self) -> int:
        self._write(self.addr_abs, self.x)
        return 0

    def _STY(self) -> int:
        self._write(self.addr_abs, self.y)
        return 0

    def _TAX(self) -> int:
        self.x = self.a & 0xFF
        self._set_zn(self.x)
        return 0

    def _TAY(self) -> int:
        self.y = self.a & 0xFF
        self._set_zn(self.y)
        return 0

    def _TXA(self) -> int:
        self.a = self.x & 0xFF
        self._set_zn(self.a)
        return 0

    def _TYA(self) -> int:
        self.a = self.y & 0xFF
        self._set_zn(self.a)
        return 0

    def _TSX(self) -> int:
        self.x = self.sp & 0xFF
        self._set_zn(self.x)
        return 0

    def _TXS(self) -> int:
        self.sp = self.x & 0xFF
        return 0

    def _INX(self) -> int:
        self.x = (self.x + 1) & 0xFF
        self._set_zn(self.x)
        return 0

    def _INY(self) -> int:
        self.y = (self.y + 1) & 0xFF
        self._set_zn(self.y)
        return 0

    def _DEX(self) -> int:
        self.x = (self.x - 1) & 0xFF
        self._set_zn(self.x)
        return 0

    def _DEY(self) -> int:
        self.y = (self.y - 1) & 0xFF
        self._set_zn(self.y)
        return 0

    def _PHA(self) -> int:
        self._push(self.a)
        return 0

    def _PHP(self) -> int:
        self._push(self.p | FLAG_B | FLAG_U)
        return 0

    def _PLA(self) -> int:
        self.a = self._pull()
        self._set_zn(self.a)
        return 0

    def _PLP(self) -> int:
        self.p = (self._pull() | FLAG_U) & ~FLAG_B
        return 0

    def _JMP(self) -> int:
        self.pc = self.addr_abs
        return 0

    def _JSR(self) -> int:
        return_addr = (self.pc - 1) & 0xFFFF
        self._push((return_addr >> 8) & 0xFF)
        self._push(return_addr & 0xFF)
        self.pc = self.addr_abs
        return 0

    def _RTS(self) -> int:
        lo = self._pull()
        hi = self._pull()
        self.pc = (((hi << 8) | lo) + 1) & 0xFFFF
        return 0

    def _RTI(self) -> int:
        self.p = (self._pull() | FLAG_U) & ~FLAG_B
        lo = self._pull()
        hi = self._pull()
        self.pc = (hi << 8) | lo
        return 0

    def _BRK(self) -> int:
        self.pc = (self.pc + 1) & 0xFFFF
        self._service_interrupt(0xFFFE, is_brk=True)
        return 0

    def _BCC(self) -> int:
        return self._branch(not self._get_flag(FLAG_C))

    def _BCS(self) -> int:
        return self._branch(bool(self._get_flag(FLAG_C)))

    def _BEQ(self) -> int:
        return self._branch(bool(self._get_flag(FLAG_Z)))

    def _BMI(self) -> int:
        return self._branch(bool(self._get_flag(FLAG_N)))

    def _BNE(self) -> int:
        return self._branch(not self._get_flag(FLAG_Z))

    def _BPL(self) -> int:
        return self._branch(not self._get_flag(FLAG_N))

    def _BVC(self) -> int:
        return self._branch(not self._get_flag(FLAG_V))

    def _BVS(self) -> int:
        return self._branch(bool(self._get_flag(FLAG_V)))

    def _CLC(self) -> int:
        self._set_flag(FLAG_C, False)
        return 0

    def _CLD(self) -> int:
        self._set_flag(FLAG_D, False)
        return 0

    def _CLI(self) -> int:
        self._set_flag(FLAG_I, False)
        return 0

    def _CLV(self) -> int:
        self._set_flag(FLAG_V, False)
        return 0

    def _SEC(self) -> int:
        self._set_flag(FLAG_C, True)
        return 0

    def _SED(self) -> int:
        self._set_flag(FLAG_D, True)
        return 0

    def _SEI(self) -> int:
        self._set_flag(FLAG_I, True)
        return 0

    def _NOP(self) -> int:
        return 0

    def _KIL(self) -> int:
        self.halted = True
        return 0

    # Undocumented operations
    def _LAX(self) -> int:
        value = self._fetch()
        self.a = value
        self.x = value
        self._set_zn(value)
        return 0

    def _SAX(self) -> int:
        self._write(self.addr_abs, self.a & self.x)
        return 0

    def _DCP(self) -> int:
        value = (self._read(self.addr_abs) - 1) & 0xFF
        self._write(self.addr_abs, value)
        temp = (self.a - value) & 0x1FF
        self._set_flag(FLAG_C, self.a >= value)
        self._set_zn(temp & 0xFF)
        return 0

    def _ISC(self) -> int:
        value = (self._read(self.addr_abs) + 1) & 0xFF
        self._write(self.addr_abs, value)
        self._SBC_value(value)
        return 0

    def _RLA(self) -> int:
        value = self._read(self.addr_abs)
        carry = self._get_flag(FLAG_C)
        self._set_flag(FLAG_C, bool(value & 0x80))
        value = ((value << 1) | carry) & 0xFF
        self._write(self.addr_abs, value)
        self.a &= value
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _RRA(self) -> int:
        value = self._read(self.addr_abs)
        carry = self._get_flag(FLAG_C)
        self._set_flag(FLAG_C, bool(value & 0x01))
        value = ((carry << 7) | (value >> 1)) & 0xFF
        self._write(self.addr_abs, value)
        self._ADC_value(value)
        return 0

    def _SLO(self) -> int:
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x80))
        value = (value << 1) & 0xFF
        self._write(self.addr_abs, value)
        self.a |= value
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _SRE(self) -> int:
        value = self._read(self.addr_abs)
        self._set_flag(FLAG_C, bool(value & 0x01))
        value = (value >> 1) & 0xFF
        self._write(self.addr_abs, value)
        self.a ^= value
        self.a &= 0xFF
        self._set_zn(self.a)
        return 0

    def _ANC(self) -> int:
        self.a &= self._fetch()
        self.a &= 0xFF
        self._set_zn(self.a)
        self._set_flag(FLAG_C, bool(self.a & 0x80))
        return 0

    def _ALR(self) -> int:
        self.a &= self._fetch()
        self._set_flag(FLAG_C, bool(self.a & 0x01))
        self.a = (self.a >> 1) & 0xFF
        self._set_zn(self.a)
        return 0

    def _ARR(self) -> int:
        self.a &= self._fetch()
        self.a = ((self._get_flag(FLAG_C) << 7) | (self.a >> 1)) & 0xFF
        self._set_zn(self.a)
        bit5 = (self.a >> 5) & 1
        bit6 = (self.a >> 6) & 1
        self._set_flag(FLAG_C, bool(bit6))
        self._set_flag(FLAG_V, bool(bit5 ^ bit6))
        return 0

    def _XAA(self) -> int:
        self.a = (self.x & self._fetch()) & 0xFF
        self._set_zn(self.a)
        return 0

    def _AXS(self) -> int:
        value = self._fetch()
        temp = (self.a & self.x) - value
        self._set_flag(FLAG_C, temp >= 0)
        self.x = temp & 0xFF
        self._set_zn(self.x)
        return 0

    def _LAS(self) -> int:
        value = self._fetch() & self.sp
        self.a = value
        self.x = value
        self.sp = value
        self._set_zn(value)
        return 0

    def _AHX(self) -> int:
        high = ((self.addr_base >> 8) + 1) & 0xFF
        addr = self.addr_abs
        if self.current_mode in (self._ABY, self._IZY):
            addr = (self.addr_base & 0xFF00) | (self.addr_abs & 0x00FF)
        value = self.a & self.x & high
        self._write(addr, value)
        return 0

    def _TAS(self) -> int:
        self.sp = self.a & self.x
        high = ((self.addr_base >> 8) + 1) & 0xFF
        addr = self.addr_abs
        if self.current_mode == self._ABY:
            addr = (self.addr_base & 0xFF00) | (self.addr_abs & 0x00FF)
        value = self.sp & high
        self._write(addr, value)
        return 0

    def _SHX(self) -> int:
        high = ((self.addr_base >> 8) + 1) & 0xFF
        addr = self.addr_abs
        if self.current_mode == self._ABY:
            addr = (self.addr_base & 0xFF00) | (self.addr_abs & 0x00FF)
        value = self.x & high
        self._write(addr, value)
        return 0

    def _SHY(self) -> int:
        high = ((self.addr_base >> 8) + 1) & 0xFF
        addr = self.addr_abs
        if self.current_mode == self._ABX:
            addr = (self.addr_base & 0xFF00) | (self.addr_abs & 0x00FF)
        value = self.y & high
        self._write(addr, value)
        return 0

    def _set(self, opcode: int, name: str, mode: AddressMode, op: Operation, cycles: int, page_cycle: bool = False) -> None:
        self.lookup[opcode] = Instruction(name, mode, op, cycles, page_cycle)

    def _build_lookup(self) -> None:
        # Official opcodes
        self._set(0x00, "BRK", self._IMP, self._BRK, 7)
        self._set(0x01, "ORA", self._IZX, self._ORA, 6)
        self._set(0x05, "ORA", self._ZP0, self._ORA, 3)
        self._set(0x06, "ASL", self._ZP0, self._ASL, 5)
        self._set(0x08, "PHP", self._IMP, self._PHP, 3)
        self._set(0x09, "ORA", self._IMM, self._ORA, 2)
        self._set(0x0A, "ASL", self._ACC, self._ASL, 2)
        self._set(0x0D, "ORA", self._ABS, self._ORA, 4)
        self._set(0x0E, "ASL", self._ABS, self._ASL, 6)
        self._set(0x10, "BPL", self._REL, self._BPL, 2)
        self._set(0x11, "ORA", self._IZY, self._ORA, 5, True)
        self._set(0x15, "ORA", self._ZPX, self._ORA, 4)
        self._set(0x16, "ASL", self._ZPX, self._ASL, 6)
        self._set(0x18, "CLC", self._IMP, self._CLC, 2)
        self._set(0x19, "ORA", self._ABY, self._ORA, 4, True)
        self._set(0x1D, "ORA", self._ABX, self._ORA, 4, True)
        self._set(0x1E, "ASL", self._ABX, self._ASL, 7)
        self._set(0x20, "JSR", self._ABS, self._JSR, 6)
        self._set(0x21, "AND", self._IZX, self._AND, 6)
        self._set(0x24, "BIT", self._ZP0, self._BIT, 3)
        self._set(0x25, "AND", self._ZP0, self._AND, 3)
        self._set(0x26, "ROL", self._ZP0, self._ROL, 5)
        self._set(0x28, "PLP", self._IMP, self._PLP, 4)
        self._set(0x29, "AND", self._IMM, self._AND, 2)
        self._set(0x2A, "ROL", self._ACC, self._ROL, 2)
        self._set(0x2C, "BIT", self._ABS, self._BIT, 4)
        self._set(0x2D, "AND", self._ABS, self._AND, 4)
        self._set(0x2E, "ROL", self._ABS, self._ROL, 6)
        self._set(0x30, "BMI", self._REL, self._BMI, 2)
        self._set(0x31, "AND", self._IZY, self._AND, 5, True)
        self._set(0x35, "AND", self._ZPX, self._AND, 4)
        self._set(0x36, "ROL", self._ZPX, self._ROL, 6)
        self._set(0x38, "SEC", self._IMP, self._SEC, 2)
        self._set(0x39, "AND", self._ABY, self._AND, 4, True)
        self._set(0x3D, "AND", self._ABX, self._AND, 4, True)
        self._set(0x3E, "ROL", self._ABX, self._ROL, 7)
        self._set(0x40, "RTI", self._IMP, self._RTI, 6)
        self._set(0x41, "EOR", self._IZX, self._EOR, 6)
        self._set(0x45, "EOR", self._ZP0, self._EOR, 3)
        self._set(0x46, "LSR", self._ZP0, self._LSR, 5)
        self._set(0x48, "PHA", self._IMP, self._PHA, 3)
        self._set(0x49, "EOR", self._IMM, self._EOR, 2)
        self._set(0x4A, "LSR", self._ACC, self._LSR, 2)
        self._set(0x4C, "JMP", self._ABS, self._JMP, 3)
        self._set(0x4D, "EOR", self._ABS, self._EOR, 4)
        self._set(0x4E, "LSR", self._ABS, self._LSR, 6)
        self._set(0x50, "BVC", self._REL, self._BVC, 2)
        self._set(0x51, "EOR", self._IZY, self._EOR, 5, True)
        self._set(0x55, "EOR", self._ZPX, self._EOR, 4)
        self._set(0x56, "LSR", self._ZPX, self._LSR, 6)
        self._set(0x58, "CLI", self._IMP, self._CLI, 2)
        self._set(0x59, "EOR", self._ABY, self._EOR, 4, True)
        self._set(0x5D, "EOR", self._ABX, self._EOR, 4, True)
        self._set(0x5E, "LSR", self._ABX, self._LSR, 7)
        self._set(0x60, "RTS", self._IMP, self._RTS, 6)
        self._set(0x61, "ADC", self._IZX, self._ADC, 6)
        self._set(0x65, "ADC", self._ZP0, self._ADC, 3)
        self._set(0x66, "ROR", self._ZP0, self._ROR, 5)
        self._set(0x68, "PLA", self._IMP, self._PLA, 4)
        self._set(0x69, "ADC", self._IMM, self._ADC, 2)
        self._set(0x6A, "ROR", self._ACC, self._ROR, 2)
        self._set(0x6C, "JMP", self._IND, self._JMP, 5)
        self._set(0x6D, "ADC", self._ABS, self._ADC, 4)
        self._set(0x6E, "ROR", self._ABS, self._ROR, 6)
        self._set(0x70, "BVS", self._REL, self._BVS, 2)
        self._set(0x71, "ADC", self._IZY, self._ADC, 5, True)
        self._set(0x75, "ADC", self._ZPX, self._ADC, 4)
        self._set(0x76, "ROR", self._ZPX, self._ROR, 6)
        self._set(0x78, "SEI", self._IMP, self._SEI, 2)
        self._set(0x79, "ADC", self._ABY, self._ADC, 4, True)
        self._set(0x7D, "ADC", self._ABX, self._ADC, 4, True)
        self._set(0x7E, "ROR", self._ABX, self._ROR, 7)
        self._set(0x81, "STA", self._IZX, self._STA, 6)
        self._set(0x84, "STY", self._ZP0, self._STY, 3)
        self._set(0x85, "STA", self._ZP0, self._STA, 3)
        self._set(0x86, "STX", self._ZP0, self._STX, 3)
        self._set(0x88, "DEY", self._IMP, self._DEY, 2)
        self._set(0x8A, "TXA", self._IMP, self._TXA, 2)
        self._set(0x8C, "STY", self._ABS, self._STY, 4)
        self._set(0x8D, "STA", self._ABS, self._STA, 4)
        self._set(0x8E, "STX", self._ABS, self._STX, 4)
        self._set(0x90, "BCC", self._REL, self._BCC, 2)
        self._set(0x91, "STA", self._IZY, self._STA, 6)
        self._set(0x94, "STY", self._ZPX, self._STY, 4)
        self._set(0x95, "STA", self._ZPX, self._STA, 4)
        self._set(0x96, "STX", self._ZPY, self._STX, 4)
        self._set(0x98, "TYA", self._IMP, self._TYA, 2)
        self._set(0x99, "STA", self._ABY, self._STA, 5)
        self._set(0x9A, "TXS", self._IMP, self._TXS, 2)
        self._set(0x9D, "STA", self._ABX, self._STA, 5)
        self._set(0xA0, "LDY", self._IMM, self._LDY, 2)
        self._set(0xA1, "LDA", self._IZX, self._LDA, 6)
        self._set(0xA2, "LDX", self._IMM, self._LDX, 2)
        self._set(0xA4, "LDY", self._ZP0, self._LDY, 3)
        self._set(0xA5, "LDA", self._ZP0, self._LDA, 3)
        self._set(0xA6, "LDX", self._ZP0, self._LDX, 3)
        self._set(0xA8, "TAY", self._IMP, self._TAY, 2)
        self._set(0xA9, "LDA", self._IMM, self._LDA, 2)
        self._set(0xAA, "TAX", self._IMP, self._TAX, 2)
        self._set(0xAC, "LDY", self._ABS, self._LDY, 4)
        self._set(0xAD, "LDA", self._ABS, self._LDA, 4)
        self._set(0xAE, "LDX", self._ABS, self._LDX, 4)
        self._set(0xB0, "BCS", self._REL, self._BCS, 2)
        self._set(0xB1, "LDA", self._IZY, self._LDA, 5, True)
        self._set(0xB4, "LDY", self._ZPX, self._LDY, 4)
        self._set(0xB5, "LDA", self._ZPX, self._LDA, 4)
        self._set(0xB6, "LDX", self._ZPY, self._LDX, 4)
        self._set(0xB8, "CLV", self._IMP, self._CLV, 2)
        self._set(0xB9, "LDA", self._ABY, self._LDA, 4, True)
        self._set(0xBA, "TSX", self._IMP, self._TSX, 2)
        self._set(0xBC, "LDY", self._ABX, self._LDY, 4, True)
        self._set(0xBD, "LDA", self._ABX, self._LDA, 4, True)
        self._set(0xBE, "LDX", self._ABY, self._LDX, 4, True)
        self._set(0xC0, "CPY", self._IMM, self._CPY, 2)
        self._set(0xC1, "CMP", self._IZX, self._CMP, 6)
        self._set(0xC4, "CPY", self._ZP0, self._CPY, 3)
        self._set(0xC5, "CMP", self._ZP0, self._CMP, 3)
        self._set(0xC6, "DEC", self._ZP0, self._DEC, 5)
        self._set(0xC8, "INY", self._IMP, self._INY, 2)
        self._set(0xC9, "CMP", self._IMM, self._CMP, 2)
        self._set(0xCA, "DEX", self._IMP, self._DEX, 2)
        self._set(0xCC, "CPY", self._ABS, self._CPY, 4)
        self._set(0xCD, "CMP", self._ABS, self._CMP, 4)
        self._set(0xCE, "DEC", self._ABS, self._DEC, 6)
        self._set(0xD0, "BNE", self._REL, self._BNE, 2)
        self._set(0xD1, "CMP", self._IZY, self._CMP, 5, True)
        self._set(0xD5, "CMP", self._ZPX, self._CMP, 4)
        self._set(0xD6, "DEC", self._ZPX, self._DEC, 6)
        self._set(0xD8, "CLD", self._IMP, self._CLD, 2)
        self._set(0xD9, "CMP", self._ABY, self._CMP, 4, True)
        self._set(0xDD, "CMP", self._ABX, self._CMP, 4, True)
        self._set(0xDE, "DEC", self._ABX, self._DEC, 7)
        self._set(0xE0, "CPX", self._IMM, self._CPX, 2)
        self._set(0xE1, "SBC", self._IZX, self._SBC, 6)
        self._set(0xE4, "CPX", self._ZP0, self._CPX, 3)
        self._set(0xE5, "SBC", self._ZP0, self._SBC, 3)
        self._set(0xE6, "INC", self._ZP0, self._INC, 5)
        self._set(0xE8, "INX", self._IMP, self._INX, 2)
        self._set(0xE9, "SBC", self._IMM, self._SBC, 2)
        self._set(0xEA, "NOP", self._IMP, self._NOP, 2)
        self._set(0xEC, "CPX", self._ABS, self._CPX, 4)
        self._set(0xED, "SBC", self._ABS, self._SBC, 4)
        self._set(0xEE, "INC", self._ABS, self._INC, 6)
        self._set(0xF0, "BEQ", self._REL, self._BEQ, 2)
        self._set(0xF1, "SBC", self._IZY, self._SBC, 5, True)
        self._set(0xF5, "SBC", self._ZPX, self._SBC, 4)
        self._set(0xF6, "INC", self._ZPX, self._INC, 6)
        self._set(0xF8, "SED", self._IMP, self._SED, 2)
        self._set(0xF9, "SBC", self._ABY, self._SBC, 4, True)
        self._set(0xFD, "SBC", self._ABX, self._SBC, 4, True)
        self._set(0xFE, "INC", self._ABX, self._INC, 7)

        # Unofficial NOPs
        for opcode, mode, cycles, page_cycle in [
            (0x1A, self._IMP, 2, False),
            (0x3A, self._IMP, 2, False),
            (0x5A, self._IMP, 2, False),
            (0x7A, self._IMP, 2, False),
            (0xDA, self._IMP, 2, False),
            (0xFA, self._IMP, 2, False),
            (0x80, self._IMM, 2, False),
            (0x82, self._IMM, 2, False),
            (0x89, self._IMM, 2, False),
            (0xC2, self._IMM, 2, False),
            (0xE2, self._IMM, 2, False),
            (0x04, self._ZP0, 3, False),
            (0x44, self._ZP0, 3, False),
            (0x64, self._ZP0, 3, False),
            (0x14, self._ZPX, 4, False),
            (0x34, self._ZPX, 4, False),
            (0x54, self._ZPX, 4, False),
            (0x74, self._ZPX, 4, False),
            (0xD4, self._ZPX, 4, False),
            (0xF4, self._ZPX, 4, False),
            (0x0C, self._ABS, 4, False),
            (0x1C, self._ABX, 4, True),
            (0x3C, self._ABX, 4, True),
            (0x5C, self._ABX, 4, True),
            (0x7C, self._ABX, 4, True),
            (0xDC, self._ABX, 4, True),
            (0xFC, self._ABX, 4, True),
        ]:
            self._set(opcode, "NOP", mode, self._NOP, cycles, page_cycle)

        # KIL / JAM opcodes
        for opcode in [0x02, 0x12, 0x22, 0x32, 0x42, 0x52, 0x62, 0x72, 0x92, 0xB2, 0xD2, 0xF2]:
            self._set(opcode, "KIL", self._IMP, self._KIL, 2)

        # Unofficial ALU and memory opcodes
        for opcode, mode, op, cycles, page_cycle in [
            (0x03, self._IZX, self._SLO, 8, False),
            (0x07, self._ZP0, self._SLO, 5, False),
            (0x0F, self._ABS, self._SLO, 6, False),
            (0x13, self._IZY, self._SLO, 8, False),
            (0x17, self._ZPX, self._SLO, 6, False),
            (0x1B, self._ABY, self._SLO, 7, False),
            (0x1F, self._ABX, self._SLO, 7, False),
            (0x23, self._IZX, self._RLA, 8, False),
            (0x27, self._ZP0, self._RLA, 5, False),
            (0x2F, self._ABS, self._RLA, 6, False),
            (0x33, self._IZY, self._RLA, 8, False),
            (0x37, self._ZPX, self._RLA, 6, False),
            (0x3B, self._ABY, self._RLA, 7, False),
            (0x3F, self._ABX, self._RLA, 7, False),
            (0x43, self._IZX, self._SRE, 8, False),
            (0x47, self._ZP0, self._SRE, 5, False),
            (0x4F, self._ABS, self._SRE, 6, False),
            (0x53, self._IZY, self._SRE, 8, False),
            (0x57, self._ZPX, self._SRE, 6, False),
            (0x5B, self._ABY, self._SRE, 7, False),
            (0x5F, self._ABX, self._SRE, 7, False),
            (0x63, self._IZX, self._RRA, 8, False),
            (0x67, self._ZP0, self._RRA, 5, False),
            (0x6F, self._ABS, self._RRA, 6, False),
            (0x73, self._IZY, self._RRA, 8, False),
            (0x77, self._ZPX, self._RRA, 6, False),
            (0x7B, self._ABY, self._RRA, 7, False),
            (0x7F, self._ABX, self._RRA, 7, False),
            (0x83, self._IZX, self._SAX, 6, False),
            (0x87, self._ZP0, self._SAX, 3, False),
            (0x8F, self._ABS, self._SAX, 4, False),
            (0x97, self._ZPY, self._SAX, 4, False),
            (0xA3, self._IZX, self._LAX, 6, False),
            (0xA7, self._ZP0, self._LAX, 3, False),
            (0xAB, self._IMM, self._LAX, 2, False),
            (0xAF, self._ABS, self._LAX, 4, False),
            (0xB3, self._IZY, self._LAX, 5, True),
            (0xB7, self._ZPY, self._LAX, 4, False),
            (0xBF, self._ABY, self._LAX, 4, True),
            (0xC3, self._IZX, self._DCP, 8, False),
            (0xC7, self._ZP0, self._DCP, 5, False),
            (0xCF, self._ABS, self._DCP, 6, False),
            (0xD3, self._IZY, self._DCP, 8, False),
            (0xD7, self._ZPX, self._DCP, 6, False),
            (0xDB, self._ABY, self._DCP, 7, False),
            (0xDF, self._ABX, self._DCP, 7, False),
            (0xE3, self._IZX, self._ISC, 8, False),
            (0xE7, self._ZP0, self._ISC, 5, False),
            (0xEB, self._IMM, self._SBC, 2, False),
            (0xEF, self._ABS, self._ISC, 6, False),
            (0xF3, self._IZY, self._ISC, 8, False),
            (0xF7, self._ZPX, self._ISC, 6, False),
            (0xFB, self._ABY, self._ISC, 7, False),
            (0xFF, self._ABX, self._ISC, 7, False),
            (0x0B, self._IMM, self._ANC, 2, False),
            (0x2B, self._IMM, self._ANC, 2, False),
            (0x4B, self._IMM, self._ALR, 2, False),
            (0x6B, self._IMM, self._ARR, 2, False),
            (0x8B, self._IMM, self._XAA, 2, False),
            (0xCB, self._IMM, self._AXS, 2, False),
            (0x9B, self._ABY, self._TAS, 5, False),
            (0x93, self._IZY, self._AHX, 6, False),
            (0x9F, self._ABY, self._AHX, 5, False),
            (0x9E, self._ABY, self._SHX, 5, False),
            (0x9C, self._ABX, self._SHY, 5, False),
            (0xBB, self._ABY, self._LAS, 4, True),
        ]:
            self._set(opcode, "UND", mode, op, cycles, page_cycle)
