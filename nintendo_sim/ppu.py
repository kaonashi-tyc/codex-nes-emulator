from __future__ import annotations

from dataclasses import dataclass, field

from .mapper import (
    MIRROR_FOUR_SCREEN,
    MIRROR_HORIZONTAL,
    MIRROR_SINGLE0,
    MIRROR_SINGLE1,
    MIRROR_VERTICAL,
)
from .palette import NES_RGB_PALETTE
from .rom import Cartridge


def _reverse_bits(byte: int) -> int:
    byte = ((byte & 0xF0) >> 4) | ((byte & 0x0F) << 4)
    byte = ((byte & 0xCC) >> 2) | ((byte & 0x33) << 2)
    byte = ((byte & 0xAA) >> 1) | ((byte & 0x55) << 1)
    return byte & 0xFF


POWER_UP_PALETTE = (
    0x09,
    0x01,
    0x00,
    0x01,
    0x00,
    0x02,
    0x02,
    0x0D,
    0x08,
    0x10,
    0x08,
    0x24,
    0x00,
    0x00,
    0x04,
    0x2C,
    0x09,
    0x01,
    0x34,
    0x03,
    0x00,
    0x04,
    0x00,
    0x14,
    0x08,
    0x3A,
    0x00,
    0x02,
    0x00,
    0x20,
    0x2C,
    0x08,
)


@dataclass
class PPU:
    cartridge: Cartridge
    nametable: list[bytearray] = field(default_factory=lambda: [bytearray(0x400) for _ in range(4)])
    palette_ram: bytearray = field(default_factory=lambda: bytearray(32))
    oam: bytearray = field(default_factory=lambda: bytearray(256))

    ctrl: int = 0
    mask: int = 0
    status: int = 0
    oam_addr: int = 0
    rendering_enabled: bool = False
    dynamic_mirroring: bool = False
    cached_mirroring: str = MIRROR_HORIZONTAL

    vram_addr: int = 0
    tram_addr: int = 0
    fine_x: int = 0
    address_latch: int = 0
    ppu_data_buffer: int = 0

    scanline: int = -1
    cycle: int = 0
    odd_frame: bool = False
    frame_complete: bool = False
    nmi: bool = False
    nmi_occurred: bool = False
    nmi_output: bool = False
    nmi_previous: bool = False
    nmi_delay: int = 0
    nmi_hold: int = 0
    suppress_vblank: bool = False
    suppress_nmi: bool = False
    odd_skip_latch: bool = False

    bg_next_tile_id: int = 0
    bg_next_tile_attr: int = 0
    bg_next_tile_lsb: int = 0
    bg_next_tile_msb: int = 0

    bg_shifter_pattern_lo: int = 0
    bg_shifter_pattern_hi: int = 0
    bg_shifter_attr_lo: int = 0
    bg_shifter_attr_hi: int = 0

    sprite_scanline: list[list[int]] = field(default_factory=lambda: [[0, 0, 0, 0] for _ in range(8)])
    sprite_count: int = 0
    sprite_shifter_pattern_lo: list[int] = field(default_factory=lambda: [0] * 8)
    sprite_shifter_pattern_hi: list[int] = field(default_factory=lambda: [0] * 8)
    sprite_zero_hit_possible: bool = False
    sprite_zero_being_rendered: bool = False
    eval_sprite_scanline: list[list[int]] = field(default_factory=lambda: [[0, 0, 0, 0] for _ in range(8)])
    eval_sprite_count: int = 0
    eval_sprite_zero_possible: bool = False
    eval_oam_n: int = 0
    eval_oam_m: int = 0
    eval_read_byte: int = 0
    eval_overflow_mode: bool = False
    eval_done: bool = True

    frame_rgb: bytearray = field(default_factory=lambda: bytearray(256 * 240 * 3))

    def _nmi_change(self) -> None:
        nmi_line = self.nmi_output and self.nmi_occurred
        if nmi_line and not self.nmi_previous:
            # NMI isn't instantaneous on hardware.
            self.nmi_delay = 14
            self.nmi_hold = 2
        self.nmi_previous = nmi_line

    def _set_vblank(self, active: bool) -> None:
        if active:
            self.status |= 0x80
        else:
            self.status &= ~0x80
        self.nmi_occurred = active
        self._nmi_change()

    def reset(self) -> None:
        self.ctrl = 0
        self.mask = 0
        self.status = 0
        self.oam_addr = 0
        self.rendering_enabled = False
        mapper_mirroring = self.cartridge.mapper.mirroring()
        if mapper_mirroring is None:
            self.dynamic_mirroring = False
            self.cached_mirroring = self.cartridge.mirroring
        else:
            self.dynamic_mirroring = True
            self.cached_mirroring = mapper_mirroring
        self.vram_addr = 0
        self.tram_addr = 0
        self.fine_x = 0
        self.address_latch = 0
        self.ppu_data_buffer = 0
        self.scanline = -1
        self.cycle = 0
        self.odd_frame = False
        self.frame_complete = False
        self.nmi = False
        self.nmi_occurred = False
        self.nmi_output = False
        self.nmi_previous = False
        self.nmi_delay = 0
        self.nmi_hold = 0
        self.suppress_vblank = False
        self.suppress_nmi = False
        self.odd_skip_latch = False
        self.bg_next_tile_id = 0
        self.bg_next_tile_attr = 0
        self.bg_next_tile_lsb = 0
        self.bg_next_tile_msb = 0
        self.bg_shifter_pattern_lo = 0
        self.bg_shifter_pattern_hi = 0
        self.bg_shifter_attr_lo = 0
        self.bg_shifter_attr_hi = 0
        self.sprite_count = 0
        self.sprite_zero_hit_possible = False
        self.sprite_zero_being_rendered = False
        self.eval_sprite_scanline = [[0, 0, 0, 0] for _ in range(8)]
        self.eval_sprite_count = 0
        self.eval_sprite_zero_possible = False
        self.eval_oam_n = 0
        self.eval_oam_m = 0
        self.eval_read_byte = 0
        self.eval_overflow_mode = False
        self.eval_done = True
        for i, value in enumerate(POWER_UP_PALETTE):
            self.palette_ram[i] = value

    def _increment_scroll_x(self) -> None:
        if not self.rendering_enabled:
            return
        if (self.vram_addr & 0x001F) == 31:
            self.vram_addr &= ~0x001F
            self.vram_addr ^= 0x0400
        else:
            self.vram_addr = (self.vram_addr + 1) & 0x7FFF

    def _increment_scroll_y(self) -> None:
        if not self.rendering_enabled:
            return
        if (self.vram_addr & 0x7000) != 0x7000:
            self.vram_addr += 0x1000
        else:
            self.vram_addr &= ~0x7000
            y = (self.vram_addr & 0x03E0) >> 5
            if y == 29:
                y = 0
                self.vram_addr ^= 0x0800
            elif y == 31:
                y = 0
            else:
                y += 1
            self.vram_addr = (self.vram_addr & ~0x03E0) | (y << 5)
        self.vram_addr &= 0x7FFF

    def _transfer_address_x(self) -> None:
        if not self.rendering_enabled:
            return
        self.vram_addr = (self.vram_addr & ~0x041F) | (self.tram_addr & 0x041F)

    def _transfer_address_y(self) -> None:
        if not self.rendering_enabled:
            return
        self.vram_addr = (self.vram_addr & ~0x7BE0) | (self.tram_addr & 0x7BE0)

    def _load_background_shifters(self) -> None:
        self.bg_shifter_pattern_lo = (self.bg_shifter_pattern_lo & 0xFF00) | self.bg_next_tile_lsb
        self.bg_shifter_pattern_hi = (self.bg_shifter_pattern_hi & 0xFF00) | self.bg_next_tile_msb
        attr_lo = 0xFF if (self.bg_next_tile_attr & 0x01) else 0x00
        attr_hi = 0xFF if (self.bg_next_tile_attr & 0x02) else 0x00
        self.bg_shifter_attr_lo = (self.bg_shifter_attr_lo & 0xFF00) | attr_lo
        self.bg_shifter_attr_hi = (self.bg_shifter_attr_hi & 0xFF00) | attr_hi

    def _update_shifters(self) -> None:
        if self.mask & 0x08:
            self.bg_shifter_pattern_lo = (self.bg_shifter_pattern_lo << 1) & 0xFFFF
            self.bg_shifter_pattern_hi = (self.bg_shifter_pattern_hi << 1) & 0xFFFF
            self.bg_shifter_attr_lo = (self.bg_shifter_attr_lo << 1) & 0xFFFF
            self.bg_shifter_attr_hi = (self.bg_shifter_attr_hi << 1) & 0xFFFF
        # Sprite shifters/counters advance only on visible dots.
        if (self.mask & 0x10) and (0 <= self.scanline < 240) and (2 <= self.cycle <= 256):
            for i in range(self.sprite_count):
                if self.sprite_scanline[i][3] > 0:
                    self.sprite_scanline[i][3] -= 1
                else:
                    self.sprite_shifter_pattern_lo[i] = (self.sprite_shifter_pattern_lo[i] << 1) & 0xFF
                    self.sprite_shifter_pattern_hi[i] = (self.sprite_shifter_pattern_hi[i] << 1) & 0xFF

    def _resolve_mirroring(self) -> str:
        if not self.dynamic_mirroring:
            return self.cached_mirroring
        mapper_mirroring = self.cartridge.mapper.mirroring()
        if mapper_mirroring is not None:
            self.cached_mirroring = mapper_mirroring
        return self.cached_mirroring

    def _map_nametable_addr(self, addr: int) -> tuple[int, int]:
        addr &= 0x0FFF
        table = (addr // 0x400) & 0x03
        index = addr & 0x03FF
        mirroring = self._resolve_mirroring()
        if mirroring == MIRROR_FOUR_SCREEN:
            return table, index
        if mirroring == MIRROR_VERTICAL:
            return table & 0x01, index
        if mirroring == MIRROR_HORIZONTAL:
            return 0 if table in (0, 1) else 1, index
        if mirroring == MIRROR_SINGLE0:
            return 0, index
        if mirroring == MIRROR_SINGLE1:
            return 1, index
        return table & 0x01, index

    def ppu_read(self, addr: int) -> int:
        addr &= 0x3FFF
        if addr <= 0x1FFF:
            return self.cartridge.mapper.ppu_read(addr)
        if addr <= 0x3EFF:
            table, index = self._map_nametable_addr(addr - 0x2000)
            return self.nametable[table][index]
        palette_addr = addr & 0x001F
        if palette_addr in (0x10, 0x14, 0x18, 0x1C):
            palette_addr -= 0x10
        return self.palette_ram[palette_addr] & 0x3F

    def ppu_write(self, addr: int, value: int) -> None:
        addr &= 0x3FFF
        value &= 0xFF
        if addr <= 0x1FFF:
            self.cartridge.mapper.ppu_write(addr, value)
            return
        if addr <= 0x3EFF:
            table, index = self._map_nametable_addr(addr - 0x2000)
            self.nametable[table][index] = value
            return
        palette_addr = addr & 0x001F
        if palette_addr in (0x10, 0x14, 0x18, 0x1C):
            palette_addr -= 0x10
        self.palette_ram[palette_addr] = value & 0x3F

    def cpu_read(self, addr: int) -> int:
        reg = addr & 0x0007
        if reg == 0x0002:
            data = (self.status & 0xE0) | (self.ppu_data_buffer & 0x1F)
            if self.scanline == 241 and self.cycle == 1:
                self.suppress_vblank = True
                self.suppress_nmi = True
            elif self.scanline == 241 and self.cycle in (2, 3):
                self.suppress_nmi = True
                self.nmi_delay = 0
                self.nmi_hold = 0
                self.nmi = False
            self._set_vblank(False)
            self.address_latch = 0
            return data
        if reg == 0x0004:
            return self.oam[self.oam_addr]
        if reg == 0x0007:
            addr = self.vram_addr & 0x3FFF
            if addr >= 0x3F00:
                # Palette reads are unbuffered, but still perform a hidden read that updates
                # the buffer from the underlying nametable space.
                data = self.ppu_read(addr)
                self.ppu_data_buffer = self.ppu_read((addr - 0x1000) & 0x3FFF)
            else:
                data = self.ppu_data_buffer
                self.ppu_data_buffer = self.ppu_read(addr)
            increment = 32 if (self.ctrl & 0x04) else 1
            self.vram_addr = (self.vram_addr + increment) & 0x7FFF
            return data
        return 0x00

    def cpu_write(self, addr: int, value: int) -> None:
        reg = addr & 0x0007
        value &= 0xFF
        if reg == 0x0000:
            self.ctrl = value
            self.nmi_output = bool(self.ctrl & 0x80)
            self._nmi_change()
            self.tram_addr = (self.tram_addr & 0xF3FF) | ((value & 0x03) << 10)
        elif reg == 0x0001:
            self.mask = value
            self.rendering_enabled = bool(value & 0x18)
        elif reg == 0x0003:
            self.oam_addr = value
        elif reg == 0x0004:
            self.oam[self.oam_addr] = value
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        elif reg == 0x0005:
            if self.address_latch == 0:
                self.fine_x = value & 0x07
                self.tram_addr = (self.tram_addr & 0xFFE0) | (value >> 3)
                self.address_latch = 1
            else:
                self.tram_addr = (self.tram_addr & 0x8FFF) | ((value & 0x07) << 12)
                self.tram_addr = (self.tram_addr & 0xFC1F) | ((value & 0xF8) << 2)
                self.address_latch = 0
        elif reg == 0x0006:
            if self.address_latch == 0:
                self.tram_addr = (self.tram_addr & 0x00FF) | ((value & 0x3F) << 8)
                self.address_latch = 1
            else:
                self.tram_addr = (self.tram_addr & 0xFF00) | value
                self.vram_addr = self.tram_addr
                self.address_latch = 0
        elif reg == 0x0007:
            self.ppu_write(self.vram_addr, value)
            increment = 32 if (self.ctrl & 0x04) else 1
            self.vram_addr = (self.vram_addr + increment) & 0x7FFF

    def dma_write(self, start_addr: int, values: bytes) -> None:
        for index, value in enumerate(values):
            self.oam[(self.oam_addr + index) & 0xFF] = value

    def _begin_sprite_evaluation(self) -> None:
        self.eval_sprite_scanline = [[0, 0, 0, 0] for _ in range(8)]
        self.eval_sprite_count = 0
        self.eval_sprite_zero_possible = False
        self.eval_oam_n = 0
        self.eval_oam_m = 0
        self.eval_read_byte = 0
        self.eval_overflow_mode = False
        self.eval_done = False

    def _clock_sprite_evaluation(self) -> None:
        if self.eval_done:
            return
        if self.eval_oam_n >= 64:
            self.eval_done = True
            return

        # Odd cycle: read primary OAM byte.
        if self.cycle & 1:
            addr = (self.eval_oam_n * 4 + self.eval_oam_m) & 0xFF
            self.eval_read_byte = self.oam[addr]
            return

        sprite_height = 16 if (self.ctrl & 0x20) else 8
        if not self.eval_overflow_mode:
            # Collect first 8 in-range sprites for next scanline.
            if self.eval_oam_m == 0:
                diff = self.scanline - self.eval_read_byte
                if 0 <= diff < sprite_height:
                    if self.eval_sprite_count < 8:
                        slot = self.eval_sprite_count
                        self.eval_sprite_scanline[slot][0] = self.eval_read_byte
                        if self.eval_oam_n == 0:
                            self.eval_sprite_zero_possible = True
                        self.eval_oam_m = 1
                    else:
                        self.eval_overflow_mode = True
                else:
                    self.eval_oam_n += 1
                    if self.eval_oam_n >= 64:
                        self.eval_done = True
            else:
                slot = self.eval_sprite_count
                self.eval_sprite_scanline[slot][self.eval_oam_m] = self.eval_read_byte
                self.eval_oam_m += 1
                if self.eval_oam_m == 4:
                    self.eval_oam_m = 0
                    self.eval_oam_n += 1
                    self.eval_sprite_count += 1
                    if self.eval_sprite_count >= 8:
                        self.eval_overflow_mode = True
                    if self.eval_oam_n >= 64:
                        self.eval_done = True
        else:
            # Pathological overflow search: bytes are treated as Y in a diagonal pattern.
            diff = self.scanline - self.eval_read_byte
            if 0 <= diff < sprite_height:
                self.status |= 0x20
                self.eval_done = True
                return
            self.eval_oam_n += 1
            self.eval_oam_m = (self.eval_oam_m + 1) & 0x03
            if self.eval_oam_n >= 64:
                self.eval_done = True

    def consume_nmi(self) -> bool:
        if not self.nmi:
            return False
        self.nmi = False
        return True

    def clock(self) -> None:
        if self.nmi_delay > 0:
            nmi_line = self.nmi_output and self.nmi_occurred
            if self.nmi_hold > 0:
                if nmi_line:
                    self.nmi_hold -= 1
                else:
                    self.nmi_delay = 0
                    self.nmi_hold = 0
            if self.nmi_delay == 0:
                self.nmi = False
            else:
                self.nmi_delay -= 1
                if self.nmi_delay == 0:
                    self.nmi = True

        if self.scanline == -1 and self.cycle == 1:
            self._set_vblank(False)
            self.status &= ~0x40
            self.status &= ~0x20
            self.suppress_nmi = False
            self.odd_skip_latch = False

        if -1 <= self.scanline < 240:
            if self.scanline >= 0 and self.cycle == 65:
                self._begin_sprite_evaluation()
            if self.scanline >= 0 and 65 <= self.cycle <= 256 and self.rendering_enabled:
                self._clock_sprite_evaluation()

            if (2 <= self.cycle < 258) or (321 <= self.cycle < 338):
                self._update_shifters()
                phase = (self.cycle - 1) % 8
                if phase == 0:
                    self._load_background_shifters()
                    self.bg_next_tile_id = self.ppu_read(0x2000 | (self.vram_addr & 0x0FFF))
                elif phase == 2:
                    addr = 0x23C0 | (self.vram_addr & 0x0C00) | ((self.vram_addr >> 4) & 0x38) | (
                        (self.vram_addr >> 2) & 0x07
                    )
                    attr = self.ppu_read(addr)
                    if self.vram_addr & 0x0040:
                        attr >>= 4
                    if self.vram_addr & 0x0002:
                        attr >>= 2
                    self.bg_next_tile_attr = attr & 0x03
                elif phase == 4:
                    table = 0x1000 if (self.ctrl & 0x10) else 0x0000
                    fine_y = (self.vram_addr >> 12) & 0x07
                    self.bg_next_tile_lsb = self.ppu_read(table + self.bg_next_tile_id * 16 + fine_y)
                elif phase == 6:
                    table = 0x1000 if (self.ctrl & 0x10) else 0x0000
                    fine_y = (self.vram_addr >> 12) & 0x07
                    self.bg_next_tile_msb = self.ppu_read(table + self.bg_next_tile_id * 16 + fine_y + 8)
                elif phase == 7:
                    self._increment_scroll_x()

            if self.cycle == 256:
                self._increment_scroll_y()
            if self.cycle == 257:
                self._load_background_shifters()
                self._transfer_address_x()

            if self.cycle in (338, 340):
                self.bg_next_tile_id = self.ppu_read(0x2000 | (self.vram_addr & 0x0FFF))

            if self.scanline == -1 and 280 <= self.cycle < 305:
                self._transfer_address_y()

            if self.cycle == 257 and self.scanline >= 0:
                self.sprite_scanline = [[0, 0, 0, 0] for _ in range(8)]
                self.sprite_count = 0
                self.sprite_zero_hit_possible = False
                if self.rendering_enabled:
                    self.sprite_count = self.eval_sprite_count
                    self.sprite_zero_hit_possible = self.eval_sprite_zero_possible
                    for i in range(self.sprite_count):
                        self.sprite_scanline[i][0] = self.eval_sprite_scanline[i][0]
                        self.sprite_scanline[i][1] = self.eval_sprite_scanline[i][1]
                        self.sprite_scanline[i][2] = self.eval_sprite_scanline[i][2]
                        self.sprite_scanline[i][3] = self.eval_sprite_scanline[i][3]

            if self.cycle == 340:
                sprite_height = 16 if (self.ctrl & 0x20) else 8
                for i in range(self.sprite_count):
                    y = self.sprite_scanline[i][0]
                    tile = self.sprite_scanline[i][1]
                    attr = self.sprite_scanline[i][2]
                    row = self.scanline - y
                    if attr & 0x80:
                        row = sprite_height - 1 - row
                    if sprite_height == 8:
                        table = 0x1000 if (self.ctrl & 0x08) else 0x0000
                        addr = table + tile * 16 + row
                    else:
                        table = (tile & 0x01) * 0x1000
                        tile &= 0xFE
                        if row > 7:
                            tile += 1
                            row -= 8
                        addr = table + tile * 16 + row
                    lo = self.ppu_read(addr)
                    hi = self.ppu_read(addr + 8)
                    if attr & 0x40:
                        lo = _reverse_bits(lo)
                        hi = _reverse_bits(hi)
                    self.sprite_shifter_pattern_lo[i] = lo
                    self.sprite_shifter_pattern_hi[i] = hi

        if self.scanline == 241 and self.cycle == 1:
            if self.suppress_vblank:
                self._set_vblank(False)
            else:
                self._set_vblank(True)
            if self.suppress_nmi:
                self.nmi_delay = 0
                self.nmi_hold = 0
                self.nmi = False
            self.suppress_vblank = False

        if 0 <= self.scanline < 240 and 1 <= self.cycle <= 256:
            bg_pixel = 0
            bg_palette = 0
            if self.mask & 0x08:
                if (self.mask & 0x02) or (self.cycle > 8):
                    bit_mux = 0x8000 >> self.fine_x
                    p0 = 1 if (self.bg_shifter_pattern_lo & bit_mux) else 0
                    p1 = 1 if (self.bg_shifter_pattern_hi & bit_mux) else 0
                    bg_pixel = (p1 << 1) | p0
                    a0 = 1 if (self.bg_shifter_attr_lo & bit_mux) else 0
                    a1 = 1 if (self.bg_shifter_attr_hi & bit_mux) else 0
                    bg_palette = (a1 << 1) | a0

            fg_pixel = 0
            fg_palette = 0
            fg_priority = False
            self.sprite_zero_being_rendered = False
            if self.mask & 0x10:
                if (self.mask & 0x04) or (self.cycle > 8):
                    for i in range(self.sprite_count):
                        if self.sprite_scanline[i][3] == 0:
                            p0 = (self.sprite_shifter_pattern_lo[i] & 0x80) >> 7
                            p1 = (self.sprite_shifter_pattern_hi[i] & 0x80) >> 6
                            fg_pixel = p0 | p1
                            fg_palette = (self.sprite_scanline[i][2] & 0x03) + 0x04
                            fg_priority = (self.sprite_scanline[i][2] & 0x20) == 0
                            if fg_pixel != 0:
                                if i == 0:
                                    self.sprite_zero_being_rendered = True
                                break

            pixel = 0
            palette = 0
            if bg_pixel == 0 and fg_pixel == 0:
                pixel = 0
                palette = 0
            elif bg_pixel == 0 and fg_pixel > 0:
                pixel = fg_pixel
                palette = fg_palette
            elif bg_pixel > 0 and fg_pixel == 0:
                pixel = bg_pixel
                palette = bg_palette
            else:
                if fg_priority:
                    pixel = fg_pixel
                    palette = fg_palette
                else:
                    pixel = bg_pixel
                    palette = bg_palette
                if self.sprite_zero_hit_possible and self.sprite_zero_being_rendered:
                    if self.mask & 0x18:
                        clipped_left = self.cycle <= 8 and (((self.mask & 0x02) == 0) or ((self.mask & 0x04) == 0))
                        if not clipped_left:
                            self.status |= 0x40

            x = self.cycle - 1
            y = self.scanline
            palette_addr = ((palette & 0x07) << 2) | (pixel & 0x03)
            if (palette_addr & 0x13) == 0x10:
                palette_addr &= 0x0F
            color_idx = self.palette_ram[palette_addr] & 0x3F
            red, green, blue = NES_RGB_PALETTE[color_idx]
            index = (y * 256 + x) * 3
            self.frame_rgb[index + 0] = red
            self.frame_rgb[index + 1] = green
            self.frame_rgb[index + 2] = blue

        if self.rendering_enabled and self.cycle == 260 and 0 <= self.scanline < 240:
            self.cartridge.mapper.clock_scanline()

        if self.scanline == -1 and self.cycle == 338:
            self.odd_skip_latch = self.rendering_enabled

        # On odd frames with rendering enabled, pre-render dot 340 is skipped.
        if self.scanline == -1 and self.cycle == 339 and self.odd_frame and self.odd_skip_latch:
            self.cycle = 0
            self.scanline = 0
            return

        self.cycle += 1
        if self.cycle >= 341:
            self.cycle = 0
            self.scanline += 1
            if self.scanline >= 261:
                self.scanline = -1
                self.frame_complete = True
                self.odd_frame = not self.odd_frame
